import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms
from torchvision.transforms.functional import rotate as rotate_tensor


class ResidualBlock(nn.Module):
    def __init__(self, in_planes, planes, norm_fn='group', stride=1):
        super(ResidualBlock, self).__init__()
  
        self.conv1 = nn.Conv2d(in_planes, planes, kernel_size=3, padding=1, stride=stride)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, padding=1)
        self.relu = nn.ReLU(inplace=True)

        num_groups = planes // 8

        if norm_fn == 'group':
            self.norm1 = nn.GroupNorm(num_groups=num_groups, num_channels=planes)
            self.norm2 = nn.GroupNorm(num_groups=num_groups, num_channels=planes)
            if not stride == 1:
                self.norm3 = nn.GroupNorm(num_groups=num_groups, num_channels=planes)
        
        elif norm_fn == 'batch':
            self.norm1 = nn.BatchNorm2d(planes)
            self.norm2 = nn.BatchNorm2d(planes)
            if not stride == 1:
                self.norm3 = nn.BatchNorm2d(planes)
        
        elif norm_fn == 'instance':
            self.norm1 = nn.InstanceNorm2d(planes)
            self.norm2 = nn.InstanceNorm2d(planes)
            if not stride == 1:
                self.norm3 = nn.InstanceNorm2d(planes)

        elif norm_fn == 'none':
            self.norm1 = nn.Sequential()
            self.norm2 = nn.Sequential()
            if not stride == 1:
                self.norm3 = nn.Sequential()

        if stride == 1:
            self.downsample = None
        
        else:    
            self.downsample = nn.Sequential(
                nn.Conv2d(in_planes, planes, kernel_size=1, stride=stride), self.norm3)


    def forward(self, x):
        y = x
        y = self.relu(self.norm1(self.conv1(y)))
        y = self.relu(self.norm2(self.conv2(y)))

        if self.downsample is not None:
            x = self.downsample(x)

        return self.relu(x+y)



class BottleneckBlock(nn.Module):
    def __init__(self, in_planes, planes, norm_fn='group', stride=1):
        super(BottleneckBlock, self).__init__()
  
        self.conv1 = nn.Conv2d(in_planes, planes//4, kernel_size=1, padding=0)
        self.conv2 = nn.Conv2d(planes//4, planes//4, kernel_size=3, padding=1, stride=stride)
        self.conv3 = nn.Conv2d(planes//4, planes, kernel_size=1, padding=0)
        self.relu = nn.ReLU(inplace=True)

        num_groups = planes // 8

        if norm_fn == 'group':
            self.norm1 = nn.GroupNorm(num_groups=num_groups, num_channels=planes//4)
            self.norm2 = nn.GroupNorm(num_groups=num_groups, num_channels=planes//4)
            self.norm3 = nn.GroupNorm(num_groups=num_groups, num_channels=planes)
            if not stride == 1:
                self.norm4 = nn.GroupNorm(num_groups=num_groups, num_channels=planes)
        
        elif norm_fn == 'batch':
            self.norm1 = nn.BatchNorm2d(planes//4)
            self.norm2 = nn.BatchNorm2d(planes//4)
            self.norm3 = nn.BatchNorm2d(planes)
            if not stride == 1:
                self.norm4 = nn.BatchNorm2d(planes)
        
        elif norm_fn == 'instance':
            self.norm1 = nn.InstanceNorm2d(planes//4)
            self.norm2 = nn.InstanceNorm2d(planes//4)
            self.norm3 = nn.InstanceNorm2d(planes)
            if not stride == 1:
                self.norm4 = nn.InstanceNorm2d(planes)

        elif norm_fn == 'none':
            self.norm1 = nn.Sequential()
            self.norm2 = nn.Sequential()
            self.norm3 = nn.Sequential()
            if not stride == 1:
                self.norm4 = nn.Sequential()

        if stride == 1:
            self.downsample = None
        
        else:    
            self.downsample = nn.Sequential(
                nn.Conv2d(in_planes, planes, kernel_size=1, stride=stride), self.norm4)


    def forward(self, x):
        y = x
        y = self.relu(self.norm1(self.conv1(y)))
        y = self.relu(self.norm2(self.conv2(y)))
        y = self.relu(self.norm3(self.conv3(y)))

        if self.downsample is not None:
            x = self.downsample(x)

        return self.relu(x+y)

class BasicEncoder(nn.Module):
    def __init__(self, output_dim=128, norm_fn='batch', dropout=0.0):
        super(BasicEncoder, self).__init__()
        self.norm_fn = norm_fn

        if self.norm_fn == 'group':
            self.norm1 = nn.GroupNorm(num_groups=8, num_channels=64)
            
        elif self.norm_fn == 'batch':
            self.norm1 = nn.BatchNorm2d(64)

        elif self.norm_fn == 'instance':
            self.norm1 = nn.InstanceNorm2d(64)

        elif self.norm_fn == 'none':
            self.norm1 = nn.Sequential()

        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3)
        self.relu1 = nn.ReLU(inplace=True)

        self.in_planes = 64
        self.layer1 = self._make_layer(64,  stride=1)
        self.layer2 = self._make_layer(96, stride=2)
        self.layer3 = self._make_layer(128, stride=2)

        # output convolution
        self.conv2 = nn.Conv2d(128, output_dim, kernel_size=1)

        self.dropout = None
        if dropout > 0:
            self.dropout = nn.Dropout2d(p=dropout)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.InstanceNorm2d, nn.GroupNorm)):
                if m.weight is not None:
                    nn.init.constant_(m.weight, 1)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def _make_layer(self, dim, stride=1):
        layer1 = ResidualBlock(self.in_planes, dim, self.norm_fn, stride=stride)
        layer2 = ResidualBlock(dim, dim, self.norm_fn, stride=1)
        layers = (layer1, layer2)
        
        self.in_planes = dim
        return nn.Sequential(*layers)


    def forward(self, x):

        # if input is list, combine batch dimension
        is_list = isinstance(x, tuple) or isinstance(x, list)
        if is_list:
            batch_dim = x[0].shape[0]
            x = torch.cat(x, dim=0)

        x = self.conv1(x)
        x = self.norm1(x)
        x = self.relu1(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)

        x = self.conv2(x)

        if self.training and self.dropout is not None:
            x = self.dropout(x)

        if is_list:
            x = torch.split(x, [batch_dim, batch_dim], dim=0)

        return x


class SmallEncoder(nn.Module):
    def __init__(self, output_dim=128, norm_fn='batch', dropout=0.0):
        super(SmallEncoder, self).__init__()
        self.norm_fn = norm_fn

        if self.norm_fn == 'group':
            self.norm1 = nn.GroupNorm(num_groups=8, num_channels=32)
            
        elif self.norm_fn == 'batch':
            self.norm1 = nn.BatchNorm2d(32)

        elif self.norm_fn == 'instance':
            self.norm1 = nn.InstanceNorm2d(32)

        elif self.norm_fn == 'none':
            self.norm1 = nn.Sequential()

        self.conv1 = nn.Conv2d(3, 32, kernel_size=7, stride=2, padding=3)
        self.relu1 = nn.ReLU(inplace=True)

        self.in_planes = 32
        self.layer1 = self._make_layer(32,  stride=1)
        self.layer2 = self._make_layer(64, stride=2)
        self.layer3 = self._make_layer(96, stride=2)

        self.dropout = None
        if dropout > 0:
            self.dropout = nn.Dropout2d(p=dropout)
        
        self.conv2 = nn.Conv2d(96, output_dim, kernel_size=1)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.InstanceNorm2d, nn.GroupNorm)):
                if m.weight is not None:
                    nn.init.constant_(m.weight, 1)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def _make_layer(self, dim, stride=1):
        layer1 = BottleneckBlock(self.in_planes, dim, self.norm_fn, stride=stride)
        layer2 = BottleneckBlock(dim, dim, self.norm_fn, stride=1)
        layers = (layer1, layer2)
    
        self.in_planes = dim
        return nn.Sequential(*layers)


    def forward(self, x):

        # if input is list, combine batch dimension
        is_list = isinstance(x, tuple) or isinstance(x, list)
        if is_list:
            batch_dim = x[0].shape[0]
            x = torch.cat(x, dim=0)

        x = self.conv1(x)
        x = self.norm1(x)
        x = self.relu1(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.conv2(x)

        if self.training and self.dropout is not None:
            x = self.dropout(x)

        if is_list:
            x = torch.split(x, [batch_dim, batch_dim], dim=0)

        return x

class PositionalEncoding(nn.Module):
    """ Positional encoding. """
    def __init__(self, num_hiddens, dropout=0.0, max_len=10000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(dropout)
        # Create a long enough P
        self.P = torch.zeros((1, max_len, num_hiddens))
        X = torch.arange(1, max_len + 1, dtype=torch.float32).reshape(-1, 1) \
            / torch.pow(10000, torch.arange(0, num_hiddens, 2, dtype=torch.float32) / num_hiddens)
        self.sinx = torch.sin(X)
        self.cosx = torch.cos(X)
        self.P[:, :, 0::2] = self.sinx
        self.P[:, :, 1::2] = self.cosx

    def forward(self, X):
        X = X + self.P[:, :X.shape[1], :].to(X.device)
        return self.dropout(X)

    def to_relatvive(self, X):
        all_sin = torch.clone(X[:, :, 0::2])
        all_cos = torch.clone(X[:, :, 1::2])
        sinx = self.sinx[:all_sin.shape[1], :].to(X.device)
        cosx = self.cosx[:all_cos.shape[1], :].to(X.device) 
        X[:, :, 0::2] = all_sin * cosx - all_cos * sinx
        X[:, :, 1::2] = all_cos * cosx + all_sin * sinx
        return X

class CoordinateSetAttention(nn.Module):
    def __init__(self, feature_size=128, enc_size=64, heads=4, bias=True, dropout=0.0):
        super(CoordinateSetAttention, self).__init__()
        self.feature_size = feature_size
        self.enc_size = enc_size    # Final result will have a dimension of 4 * `enc_size`
        self.att = nn.MultiheadAttention(feature_size, heads, dropout=dropout, bias=bias,
                                            batch_first=True)
        self.pos_enc = PositionalEncoding(feature_size)
    
    def __get_attention_result(self, mat, final_shape, mask=None):
        # Convert feature map to attention friendly format
        mat = mat.reshape(-1, mat.shape[-2], self.feature_size)

        # Get positional encoding
        mat_vals = self.pos_enc(torch.zeros_like(mat).to(mat.device))

        # Calculate output, convert to relative, retain only `enc_size' position elements from each
        if mask is not None:
            mask = mask.view(*((-1, ) + mask.shape[2:]))
            mat_res = self.pos_enc.to_relatvive(self.att(mat, mat, mat_vals, key_padding_mask=mask)[0])
        else:
            mat_res = self.pos_enc.to_relatvive(self.att(mat, mat, mat_vals)[0])
        mat_res = mat_res.reshape(*final_shape)[:, :, :, :self.enc_size]

        return mat_res
    
    def forward(self, x):
        assert len(x.shape) == 4
        assert x.shape[1] == self.feature_size

        C_SHAPE = (x.shape[0], x.shape[2], x.shape[3], x.shape[1])
        H, W = C_SHAPE[1], C_SHAPE[2]
        PADDING_VALUES = (W // 2, W // 2, H // 2, H // 2)
        C_ANGLE, CC_ANGLE = 45, -45
        CHANNEL_PERMUTE = (0, 2, 3, 1)
        REV_CHANNEL_PERMUTE = (0, 3, 1, 2)

        # Put channels in the last dimension and define helpers
        row_x = torch.permute(x, CHANNEL_PERMUTE)
        col_x = torch.permute(x, (0, 3, 2, 1))
        padded_x = torch.nn.functional.pad(x, pad=PADDING_VALUES)
        mask_x = torch.nn.functional.pad(torch.ones(*C_SHAPE[:-1], device=row_x.device), pad=PADDING_VALUES)

        # Get the attention results
        row_res = self.__get_attention_result(row_x, row_x.shape)   # Rows

        col_res = self.__get_attention_result(col_x, col_x.shape)   # Columns
        col_res = torch.permute(col_res, (0, 2, 1, 3))  # Make `col_res` similar to `row_res`
        
        rotated_x = torch.permute(rotate_tensor(padded_x, C_ANGLE), CHANNEL_PERMUTE)    # Clockwise rotation
        rotated_mask = rotate_tensor(mask_x, C_ANGLE, interpolation=torchvision.transforms.InterpolationMode.NEAREST)
        c_rotated_res = self.__get_attention_result(rotated_x, rotated_x.shape, mask=rotated_mask)
        # Get the actual corresponding part
        c_rotated_res = torch.permute(c_rotated_res, REV_CHANNEL_PERMUTE)
        c_rotated_res = rotate_tensor(c_rotated_res, -C_ANGLE)[..., PADDING_VALUES[2]:PADDING_VALUES[2] + H,
                                                               PADDING_VALUES[0]:PADDING_VALUES[0] + W]
        c_rotated_res = torch.permute(c_rotated_res, CHANNEL_PERMUTE)
        
        rotated_x = torch.permute(rotate_tensor(padded_x, CC_ANGLE), CHANNEL_PERMUTE)    # Counter-clockwise rotation
        rotated_mask = rotate_tensor(mask_x, CC_ANGLE, interpolation=torchvision.transforms.InterpolationMode.NEAREST)
        cc_rotated_res = self.__get_attention_result(rotated_x, rotated_x.shape, mask=rotated_mask)
        # Get the actual corresponding part
        cc_rotated_res = torch.permute(cc_rotated_res, REV_CHANNEL_PERMUTE)
        cc_rotated_res = rotate_tensor(cc_rotated_res, -CC_ANGLE)[..., PADDING_VALUES[2]:PADDING_VALUES[2] + H,
                                                               PADDING_VALUES[0]:PADDING_VALUES[0] + W]
        cc_rotated_res = torch.permute(cc_rotated_res, CHANNEL_PERMUTE)
        
        # Concatenate results, sort, and setup the output
        res = torch.stack([row_res, col_res, c_rotated_res, cc_rotated_res], dim=-2)
        res = torch.sort(res, dim=-2).values.view(*(res.shape[:-2] + (-1, )))
        return torch.cat((x, torch.permute(res, REV_CHANNEL_PERMUTE)), dim=1)
