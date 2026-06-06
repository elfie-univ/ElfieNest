"""TF-IDF分词模块 - 从vector_storage.py迁移而来"""

import re
from typing import List


def tokenize(text: str) -> List[str]:
    """对中文和英文混合句子进行简易提取关键词分词

    保留与vector_storage.py._tokenize完全相同的逻辑：
    1. 去掉非字符，只留下汉字、英文和数字
    2. 中文字符逐字拆解作为简单词袋
    3. 英文字符按空格切分，转小写
    """
    # 去掉非字符，只留下汉字、英文和数字
    cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", text)
    words = []
    for part in cleaned.split():
        if re.search(r"[\u4e00-\u9fa5]", part):
            # 中文字符逐字拆解
            words.extend(list(part))
        else:
            words.append(part.lower())
    return [w for w in words if len(w) > 0]
