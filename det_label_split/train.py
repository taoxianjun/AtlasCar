from argparse import ArgumentParser

import torch
import torch.nn as nn
from torch import optim
from torch.autograd import Variable
from torchvision import datasets
from torchvision import transforms
from torchvision.models import resnet18


def train(num_epochs, net, loaders):
    loss_func = nn.CrossEntropyLoss()
    optimizer = optim.Adam(net.parameters(), lr=0.01)
    net.train()

    # Train the model

    for epoch in range(num_epochs):
        for i, (images, labels) in enumerate(loaders):
            # gives batch data, normalize x when iterate train_loader
            b_x = Variable(images)  # batch x
            b_y = Variable(labels)  # batch y
            output = net(b_x)
            loss = loss_func(output, b_y)

            # clear gradients for this training step   
            optimizer.zero_grad()

            # backpropagation, compute gradients 
            loss.backward()
            # apply gradients             
            optimizer.step()

            print('Epoch [{}/{}], Step [{}], Loss: {:.4f}'
                  .format(epoch + 1, num_epochs, i + 1, loss.item()))


def test(net, loaders):
    # Test the model
    net.eval()
    with torch.no_grad():
        for images, labels in loaders:
            test_output = net(images)
            pred_y = torch.max(test_output, 1)[1].data.squeeze()
            print(labels, pred_y)
            accuracy = (pred_y == labels).sum().item() / float(labels.size(0))
            print(accuracy)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--dataset_path', type=str, required=True)
    parser.add_argument('--cls_num', type=int, required=True)
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    transform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Resize(size=(64, 64))
        ]
    )

    dataset = datasets.ImageFolder(
        root=args.dataset_path,
        transform=transform
    )
    print(dataset.class_to_idx)

    train_size = int(0.95 * len(dataset))
    print("train_size of dataset is", train_size)
    test_size = len(dataset) - train_size
    trainset, testset = torch.utils.data.random_split(dataset, [train_size, test_size])

    trainloader = torch.utils.data.DataLoader(trainset, batch_size=128,
                                              shuffle=True, num_workers=2, drop_last=False)

    testloader = torch.utils.data.DataLoader(testset, batch_size=1,
                                             shuffle=False, num_workers=2)
    num_epochs = 300

    net = resnet18(pretrained=True)
    net.fc = nn.Linear(512 * 1, args.cls_num)
    train(num_epochs, net, trainloader)
    torch.save(net.state_dict(), './cls.pt')
    test(net, testloader)
    x = torch.randn(1, 3, 64, 64, requires_grad=True)
    net.eval()
    torch_out = net(x)

    # Export the model
    torch.onnx.export(net,  # model being run
                      x,  # model input (or a tuple for multiple inputs)
                      "cls.onnx",  # where to save the model (can be a file or file-like object)
                      export_params=True,  # store the trained parameter weights inside the model file
                      opset_version=11,  # the ONNX version to export the model to
                      do_constant_folding=True,  # whether to execute constant folding for optimization
                      input_names=['input'],  # the model's input names
                      output_names=['output'],  # the model's output names
                      )
