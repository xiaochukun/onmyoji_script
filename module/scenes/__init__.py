from .tansuo import create_tansuo
from .yuling import create_yuling
from .yuhun import create_yuhun
from .yeyuanhuo import create_yeyuanhuo
from .huodong import create_huodong
from .tupo import  create_tupo


SCENE_BUILDERS = {
    "tansuo": create_tansuo,
    "yuling": create_yuling,
    "yuhun": create_yuhun,
    "yeyuanhuo": create_yeyuanhuo,
    "huodong": create_huodong,
    "tupo": create_tupo,
}
