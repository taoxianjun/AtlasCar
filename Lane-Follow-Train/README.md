# 简介

当由于光线问题导致需要扩大数据集重新训练循迹驾驶部分模型时使用


## 操作步骤

1.依据Lane-Follow-Train / config.yaml 配置文件中的参数名，在Lane_Follow_Train中创建新的文件夹./dataset_v4或取其他名字并将配置文件中名字同步修改

2.将标注好的训练数据集放到./dataset_v4中，配置文件中的ONNX_FILE_NAME为输出的onnx模型名，可以更改

3.启动python train.py即可，模型输出到./output中

## ATC模型转换指令

```
atc --model=lfnet.onnx --framework=5 --soc_version=Ascend310B4 --output=lfnet --input_format=ND
```
