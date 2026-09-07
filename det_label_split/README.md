# 检测模型辅助分类模型使用说明

## 1. 说明
由于模型适配工具中检测模型训练数据增强包含flip，导致一些对方向敏感的类别可能无法被正确分类，因此需要使用辅助模型来对检测模型的分类结果进行修正。
    
## 2. 数据集创建
### 2.1 检测数据集创建
打开模型适配工具创建labelme格式的数据集。
### 2.2 分类数据集创建
使用 labelme_det_to_cls.py脚本将检测数据集转换为分类数据集，使用方法如下：
```bash
python labelme_det_to_cls.py --dataset_path <dataset_path> --output_path <output_path>
```
其中，dataset_path为检测数据集路径【模型适配工具标注的数据集路径】，output_path为分类数据集路径【分类数据集需要保存的路径】。

## 3. 模型训练
使用 train.py脚本训练分类模型，使用方法如下：
```bash
python train.py --dataset_path <dataset_path> --cls_num <cls_num>
```
其中，dataset_path为分类数据集路径【2.2中分类数据集创建步骤中保存的分类数据集路径】，cls_num为分类类别数。

## 4. 模型转换
训练完成之后我们会获得一个cls.onnx模型，cls.onnx文件位于train.py同级目录下。使用如下命令将onnx模型转换为om模型【请参考atc指令使用指南进行操作】：
```bash
atc --model=cls.onnx --framework=5 --output=cls --soc_version=Ascend310B1 --input_format=NCHW
```