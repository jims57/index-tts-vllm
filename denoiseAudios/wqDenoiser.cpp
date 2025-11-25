/**
 * wqDenoiser - 基于RNNoise的音频降噪工具
 * 作者: Jimmy Gan
 * 日期: 2025-11-25
 * 
 * 支持的采样率: 8kHz, 16kHz, 22.05kHz, 24kHz, 44.1kHz, 48kHz
 * 默认采样率: 48kHz (RNNoise内部处理采样率)
 * 
 * 用法: ./wqDenoiser <输入WAV文件> [输出WAV文件] [输入采样率] [输出采样率]
 * 示例: ./wqDenoiser noising-audio/getvoice_48k_mono.wav output.wav 48000 16000
 * 
 * 参数说明:
 *   输入采样率 - 指定输入WAV文件的采样率 (默认: 从WAV头读取)
 *   输出采样率 - 指定输出WAV文件的采样率 (默认: 与输入采样率相同)
 * 
 * 性能优化:
 *   - 如果输入采样率是48kHz，跳过输入重采样
 *   - 如果输出采样率是48kHz，跳过输出重采样
 */

#include <iostream>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include <stdexcept>
#include "rnnoise-source-files/rnnoise.h"

// WAV文件头结构
#pragma pack(push, 1)
struct WavHeader {
    char riff[4];           // "RIFF"
    uint32_t fileSize;      // 文件大小 - 8
    char wave[4];           // "WAVE"
    char fmt[4];            // "fmt "
    uint32_t fmtSize;       // fmt chunk大小 (通常16)
    uint16_t audioFormat;   // 音频格式 (1=PCM)
    uint16_t numChannels;   // 声道数
    uint32_t sampleRate;    // 采样率
    uint32_t byteRate;      // 字节率
    uint16_t blockAlign;    // 块对齐
    uint16_t bitsPerSample; // 位深度
};
#pragma pack(pop)

// RNNoise处理的帧大小 (48kHz下10ms = 480样本)
const int RNNOISE_FRAME_SIZE = 480;
const int RNNOISE_SAMPLE_RATE = 48000;

/**
 * 检查文件是否为有效的WAV文件
 */
bool isValidWavFile(const char* filePath) {
    FILE* file = fopen(filePath, "rb");
    if (!file) {
        return false;
    }
    
    char header[4];
    if (fread(header, 1, 4, file) != 4) {
        fclose(file);
        return false;
    }
    fclose(file);
    
    return (header[0] == 'R' && header[1] == 'I' && 
            header[2] == 'F' && header[3] == 'F');
}

/**
 * 读取WAV文件
 * 返回: 采样数据 (转换为float, 范围[-1, 1])
 */
std::vector<float> readWavFile(const char* filePath, WavHeader& header) {
    FILE* file = fopen(filePath, "rb");
    if (!file) {
        throw std::runtime_error("无法打开输入文件");
    }
    
    // 读取WAV头
    if (fread(&header, sizeof(WavHeader), 1, file) != 1) {
        fclose(file);
        throw std::runtime_error("无法读取WAV头");
    }
    
    // 验证WAV格式
    if (strncmp(header.riff, "RIFF", 4) != 0 || 
        strncmp(header.wave, "WAVE", 4) != 0) {
        fclose(file);
        throw std::runtime_error("不是有效的WAV文件");
    }
    
    if (header.audioFormat != 1) {
        fclose(file);
        throw std::runtime_error("仅支持PCM格式的WAV文件");
    }
    
    // 跳过可能的额外fmt数据
    if (header.fmtSize > 16) {
        fseek(file, header.fmtSize - 16, SEEK_CUR);
    }
    
    // 查找data chunk
    char chunkId[4];
    uint32_t chunkSize;
    while (true) {
        if (fread(chunkId, 1, 4, file) != 4) {
            fclose(file);
            throw std::runtime_error("找不到data chunk");
        }
        if (fread(&chunkSize, sizeof(uint32_t), 1, file) != 1) {
            fclose(file);
            throw std::runtime_error("无法读取chunk大小");
        }
        if (strncmp(chunkId, "data", 4) == 0) {
            break;
        }
        fseek(file, chunkSize, SEEK_CUR);
    }
    
    // 读取音频数据
    int bytesPerSample = header.bitsPerSample / 8;
    int numSamples = chunkSize / bytesPerSample / header.numChannels;
    
    std::vector<float> samples(numSamples);
    
    if (header.bitsPerSample == 16) {
        std::vector<int16_t> rawData(numSamples * header.numChannels);
        fread(rawData.data(), sizeof(int16_t), numSamples * header.numChannels, file);
        
        // 转换为单声道float
        for (int i = 0; i < numSamples; i++) {
            if (header.numChannels == 1) {
                samples[i] = rawData[i] / 32768.0f;
            } else {
                // 多声道取平均
                float sum = 0;
                for (int ch = 0; ch < header.numChannels; ch++) {
                    sum += rawData[i * header.numChannels + ch];
                }
                samples[i] = (sum / header.numChannels) / 32768.0f;
            }
        }
    } else if (header.bitsPerSample == 8) {
        std::vector<uint8_t> rawData(numSamples * header.numChannels);
        fread(rawData.data(), sizeof(uint8_t), numSamples * header.numChannels, file);
        
        for (int i = 0; i < numSamples; i++) {
            if (header.numChannels == 1) {
                samples[i] = (rawData[i] - 128) / 128.0f;
            } else {
                float sum = 0;
                for (int ch = 0; ch < header.numChannels; ch++) {
                    sum += rawData[i * header.numChannels + ch] - 128;
                }
                samples[i] = (sum / header.numChannels) / 128.0f;
            }
        }
    } else {
        fclose(file);
        throw std::runtime_error("仅支持8位或16位WAV文件");
    }
    
    fclose(file);
    return samples;
}

/**
 * 线性插值重采样
 */
std::vector<float> resample(const std::vector<float>& input, int srcRate, int dstRate) {
    if (srcRate == dstRate) {
        return input;
    }
    
    double ratio = (double)srcRate / dstRate;
    int outputSize = (int)(input.size() / ratio);
    std::vector<float> output(outputSize);
    
    for (int i = 0; i < outputSize; i++) {
        double srcPos = i * ratio;
        int srcIdx = (int)srcPos;
        double frac = srcPos - srcIdx;
        
        if (srcIdx + 1 < (int)input.size()) {
            output[i] = input[srcIdx] * (1.0 - frac) + input[srcIdx + 1] * frac;
        } else if (srcIdx < (int)input.size()) {
            output[i] = input[srcIdx];
        } else {
            output[i] = 0;
        }
    }
    
    return output;
}

/**
 * 写入WAV文件
 */
void writeWavFile(const char* filePath, const std::vector<float>& samples, int sampleRate) {
    FILE* file = fopen(filePath, "wb");
    if (!file) {
        throw std::runtime_error("无法创建输出文件");
    }
    
    // 准备WAV头
    WavHeader header;
    memcpy(header.riff, "RIFF", 4);
    memcpy(header.wave, "WAVE", 4);
    memcpy(header.fmt, "fmt ", 4);
    header.fmtSize = 16;
    header.audioFormat = 1;  // PCM
    header.numChannels = 1;  // 单声道
    header.sampleRate = sampleRate;
    header.bitsPerSample = 16;
    header.blockAlign = header.numChannels * header.bitsPerSample / 8;
    header.byteRate = header.sampleRate * header.blockAlign;
    
    uint32_t dataSize = samples.size() * sizeof(int16_t);
    header.fileSize = sizeof(WavHeader) + 8 + dataSize - 8;
    
    // 写入WAV头
    fwrite(&header, sizeof(WavHeader), 1, file);
    
    // 写入data chunk头
    fwrite("data", 1, 4, file);
    fwrite(&dataSize, sizeof(uint32_t), 1, file);
    
    // 转换并写入音频数据
    std::vector<int16_t> outputData(samples.size());
    for (size_t i = 0; i < samples.size(); i++) {
        float sample = samples[i];
        // 限幅
        if (sample > 1.0f) sample = 1.0f;
        if (sample < -1.0f) sample = -1.0f;
        outputData[i] = (int16_t)(sample * 32767.0f);
    }
    
    fwrite(outputData.data(), sizeof(int16_t), outputData.size(), file);
    fclose(file);
}

/**
 * 使用RNNoise进行降噪处理
 */
std::vector<float> denoiseAudio(const std::vector<float>& input) {
    // 创建RNNoise状态
    DenoiseState* st = rnnoise_create(NULL);
    if (!st) {
        throw std::runtime_error("无法创建RNNoise状态");
    }
    
    int frameSize = rnnoise_get_frame_size();
    std::cout << "RNNoise帧大小: " << frameSize << " 样本" << std::endl;
    
    // 准备输出缓冲区
    std::vector<float> output(input.size());
    
    // 临时缓冲区
    std::vector<float> inFrame(frameSize);
    std::vector<float> outFrame(frameSize);
    
    // 逐帧处理
    int numFrames = (input.size() + frameSize - 1) / frameSize;
    std::cout << "处理帧数: " << numFrames << std::endl;
    
    for (int i = 0; i < numFrames; i++) {
        // 填充输入帧
        int offset = i * frameSize;
        int remaining = input.size() - offset;
        int copySize = (remaining < frameSize) ? remaining : frameSize;
        
        memset(inFrame.data(), 0, frameSize * sizeof(float));
        memcpy(inFrame.data(), input.data() + offset, copySize * sizeof(float));
        
        // RNNoise期望的输入范围是[-32768, 32767]
        for (int j = 0; j < frameSize; j++) {
            inFrame[j] *= 32768.0f;
        }
        
        // 处理
        rnnoise_process_frame(st, outFrame.data(), inFrame.data());
        
        // 转换回[-1, 1]范围
        for (int j = 0; j < frameSize; j++) {
            outFrame[j] /= 32768.0f;
        }
        
        // 复制到输出
        int outCopySize = (offset + frameSize <= (int)output.size()) ? frameSize : (output.size() - offset);
        memcpy(output.data() + offset, outFrame.data(), outCopySize * sizeof(float));
        
        // 显示进度
        if ((i + 1) % 100 == 0 || i == numFrames - 1) {
            std::cout << "\r处理进度: " << (i + 1) << "/" << numFrames << " (" 
                      << (int)((i + 1) * 100.0 / numFrames) << "%)" << std::flush;
        }
    }
    std::cout << std::endl;
    
    rnnoise_destroy(st);
    return output;
}

/**
 * 验证采样率是否支持
 */
bool isValidSampleRate(int sampleRate) {
    return sampleRate == 8000 || sampleRate == 16000 || 
           sampleRate == 22050 || sampleRate == 24000 || 
           sampleRate == 44100 || sampleRate == 48000;
}

int main(int argc, char* argv[]) {
    std::cout << "========================================" << std::endl;
    std::cout << "WQDenoiser - 基于RNNoise的音频降噪工具" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 检查命令行参数
    if (argc < 2) {
        std::cout << "\n用法: " << argv[0] << " <输入WAV文件> [输出WAV文件] [输入采样率] [输出采样率]" << std::endl;
        std::cout << "\n参数说明:" << std::endl;
        std::cout << "  输入WAV文件  - 必需，要降噪的WAV音频文件" << std::endl;
        std::cout << "  输出WAV文件  - 可选，降噪后的输出文件 (默认: denoised_output.wav)" << std::endl;
        std::cout << "  输入采样率   - 可选，指定输入文件的采样率 (默认: 从WAV头读取)" << std::endl;
        std::cout << "  输出采样率   - 可选，指定输出文件的采样率 (默认: 与输入采样率相同)" << std::endl;
        std::cout << "\n支持的采样率: 8000, 16000, 22050, 24000, 44100, 48000" << std::endl;
        std::cout << "\n示例:" << std::endl;
        std::cout << "  " << argv[0] << " input.wav" << std::endl;
        std::cout << "  " << argv[0] << " input.wav output.wav" << std::endl;
        std::cout << "  " << argv[0] << " input.wav output.wav 48000" << std::endl;
        std::cout << "  " << argv[0] << " input.wav output.wav 48000 16000" << std::endl;
        return -1;
    }
    
    const char* inputPath = argv[1];
    const char* outputPath = (argc >= 3) ? argv[2] : "denoised_output.wav";
    int inputSampleRate = (argc >= 4) ? atoi(argv[3]) : 0;   // 0表示从WAV头读取
    int outputSampleRate = (argc >= 5) ? atoi(argv[4]) : 0;  // 0表示与输入采样率相同
    
    // 验证输入采样率
    if (inputSampleRate != 0 && !isValidSampleRate(inputSampleRate)) {
        std::cerr << "错误: 不支持的输入采样率 " << inputSampleRate << std::endl;
        std::cerr << "支持的采样率: 8000, 16000, 22050, 24000, 44100, 48000" << std::endl;
        return -1;
    }
    
    // 验证输出采样率
    if (outputSampleRate != 0 && !isValidSampleRate(outputSampleRate)) {
        std::cerr << "错误: 不支持的输出采样率 " << outputSampleRate << std::endl;
        std::cerr << "支持的采样率: 8000, 16000, 22050, 24000, 44100, 48000" << std::endl;
        return -1;
    }
    
    std::cout << "\n输入文件: " << inputPath << std::endl;
    std::cout << "输出文件: " << outputPath << std::endl;
    
    try {
        // 检查是否为WAV文件
        if (!isValidWavFile(inputPath)) {
            throw std::runtime_error("输入文件不是有效的WAV文件，仅支持WAV格式");
        }
        
        // 读取WAV文件
        std::cout << "\n读取WAV文件..." << std::endl;
        WavHeader header;
        std::vector<float> samples = readWavFile(inputPath, header);
        
        // 确定输入采样率
        int actualInputSampleRate = header.sampleRate;
        if (inputSampleRate != 0) {
            actualInputSampleRate = inputSampleRate;
            std::cout << "使用指定输入采样率: " << inputSampleRate << " Hz" << std::endl;
        } else {
            std::cout << "WAV文件采样率: " << actualInputSampleRate << " Hz" << std::endl;
        }
        
        // 确定输出采样率 (默认与输入相同)
        int actualOutputSampleRate = (outputSampleRate != 0) ? outputSampleRate : actualInputSampleRate;
        if (outputSampleRate != 0) {
            std::cout << "指定输出采样率: " << actualOutputSampleRate << " Hz" << std::endl;
        }
        
        std::cout << "声道数: " << header.numChannels << std::endl;
        std::cout << "位深度: " << header.bitsPerSample << " bit" << std::endl;
        std::cout << "样本数: " << samples.size() << std::endl;
        std::cout << "时长: " << (float)samples.size() / actualInputSampleRate << " 秒" << std::endl;
        
        // 步骤1: 如果输入采样率不是48kHz，需要重采样到48kHz (RNNoise要求)
        std::vector<float> processingSamples;
        if (actualInputSampleRate != RNNOISE_SAMPLE_RATE) {
            std::cout << "\n输入重采样: " << actualInputSampleRate << " Hz -> " << RNNOISE_SAMPLE_RATE << " Hz" << std::endl;
            processingSamples = resample(samples, actualInputSampleRate, RNNOISE_SAMPLE_RATE);
            std::cout << "重采样后样本数: " << processingSamples.size() << std::endl;
        } else {
            std::cout << "\n输入采样率已是48kHz，跳过输入重采样" << std::endl;
            processingSamples = samples;
        }
        
        // 步骤2: RNNoise降噪处理 (始终在48kHz下进行)
        std::cout << "\n开始RNNoise降噪处理..." << std::endl;
        std::vector<float> denoisedSamples = denoiseAudio(processingSamples);
        
        // 步骤3: 如果输出采样率不是48kHz，需要重采样到目标采样率
        std::vector<float> outputSamples;
        if (actualOutputSampleRate != RNNOISE_SAMPLE_RATE) {
            std::cout << "\n输出重采样: " << RNNOISE_SAMPLE_RATE << " Hz -> " << actualOutputSampleRate << " Hz" << std::endl;
            outputSamples = resample(denoisedSamples, RNNOISE_SAMPLE_RATE, actualOutputSampleRate);
            std::cout << "重采样后样本数: " << outputSamples.size() << std::endl;
        } else {
            std::cout << "\n输出采样率是48kHz，跳过输出重采样" << std::endl;
            outputSamples = denoisedSamples;
        }
        
        // 写入输出文件
        std::cout << "\n写入输出文件..." << std::endl;
        writeWavFile(outputPath, outputSamples, actualOutputSampleRate);
        
        std::cout << "\n========================================" << std::endl;
        std::cout << "降噪完成!" << std::endl;
        std::cout << "输出文件: " << outputPath << std::endl;
        std::cout << "输出采样率: " << actualOutputSampleRate << " Hz" << std::endl;
        std::cout << "========================================" << std::endl;
        
        return 0;
        
    } catch (const std::exception& e) {
        std::cerr << "\n错误: " << e.what() << std::endl;
        return -1;
    }
}