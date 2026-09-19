"""The PANNs Cnn14 sound-recognition network, for inference only.

Adapted from panns_inference 0.1.1 by Qiuqiang Kong
(https://github.com/qiuqiangkong/panns_inference, MIT licence), from the paper
"PANNs: Large-Scale Pretrained Audio Neural Networks for Audio Pattern
Recognition" (Kong et al., 2020).

Why this is copied rather than imported: importing *any* part of that package
runs its config module, which downloads a label file with `wget` into the
user's home folder. Windows has no `wget`, so the download silently fails and
the import crashes, and the spec (section 10) wants model files in the
creator's chosen models folder anyway. The network definition below is
unchanged apart from removing training-only parts (SpecAugment, mixup,
dropout), which never run during inference, so the published weights load
exactly.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchlibrosa.stft import LogmelFilterBank, Spectrogram

SAMPLE_RATE = 32_000


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=(3, 3),
                               stride=(1, 1), padding=(1, 1), bias=False)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=(3, 3),
                               stride=(1, 1), padding=(1, 1), bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.bn2 = nn.BatchNorm2d(out_channels)

    def forward(self, x: torch.Tensor, pool_size: tuple[int, int] = (2, 2)) -> torch.Tensor:
        x = F.relu_(self.bn1(self.conv1(x)))
        x = F.relu_(self.bn2(self.conv2(x)))
        return F.avg_pool2d(x, kernel_size=pool_size)


class Cnn14(nn.Module):
    """Tags 527 AudioSet sound classes in a clip of 32 kHz mono audio."""

    def __init__(self, classes_num: int = 527) -> None:
        super().__init__()
        self.spectrogram_extractor = Spectrogram(
            n_fft=1024, hop_length=320, win_length=1024, window="hann",
            center=True, pad_mode="reflect", freeze_parameters=True,
        )
        self.logmel_extractor = LogmelFilterBank(
            sr=SAMPLE_RATE, n_fft=1024, n_mels=64, fmin=50, fmax=14000,
            ref=1.0, amin=1e-10, top_db=None, freeze_parameters=True,
        )
        self.bn0 = nn.BatchNorm2d(64)
        self.conv_block1 = ConvBlock(1, 64)
        self.conv_block2 = ConvBlock(64, 128)
        self.conv_block3 = ConvBlock(128, 256)
        self.conv_block4 = ConvBlock(256, 512)
        self.conv_block5 = ConvBlock(512, 1024)
        self.conv_block6 = ConvBlock(1024, 2048)
        self.fc1 = nn.Linear(2048, 2048, bias=True)
        self.fc_audioset = nn.Linear(2048, classes_num, bias=True)

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        """(batch, samples) -> (batch, 527) probabilities between 0 and 1."""
        x = self.spectrogram_extractor(waveform)
        x = self.logmel_extractor(x)
        x = self.bn0(x.transpose(1, 3)).transpose(1, 3)
        for block in (self.conv_block1, self.conv_block2, self.conv_block3,
                      self.conv_block4, self.conv_block5):
            x = block(x, pool_size=(2, 2))
        x = self.conv_block6(x, pool_size=(1, 1))
        x = torch.mean(x, dim=3)
        x = torch.max(x, dim=2).values + torch.mean(x, dim=2)
        x = F.relu_(self.fc1(x))
        return torch.sigmoid(self.fc_audioset(x))
