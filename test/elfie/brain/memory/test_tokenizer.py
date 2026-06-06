"""分词模块单元测试

测试 tokenizer.tokenize 函数的中英文分词功能。
"""

from elfie.brain.memory.tokenizer import tokenize


class TestTokenizer:
    """测试 tokenize 分词功能"""

    def test_tokenizer_chinese(self):
        """中文分词：逐字拆解"""
        words = tokenize("我喜欢编程")
        # 每个中文字符单独拆开
        assert words == ["我", "喜", "欢", "编", "程"]

    def test_tokenizer_english(self):
        """英文分词：按空格切分，转小写"""
        words = tokenize("I love Python")
        assert words == ["i", "love", "python"]

    def test_tokenizer_mixed(self):
        """中英文混合分词"""
        words = tokenize("我爱 Python 编程")
        # 中文字符逐字拆解，英文单词保持
        assert "我" in words
        assert "爱" in words
        assert "编" in words
        assert "程" in words
        assert "python" in words

    def test_tokenizer_removes_punctuation(self):
        """标点符号被移除"""
        words = tokenize("你好，世界！")
        assert "，" not in words
        assert "！" not in words
        assert words == ["你", "好", "世", "界"]

    def test_tokenizer_empty_string(self):
        """空字符串返回空列表"""
        assert tokenize("") == []

    def test_tokenizer_only_punctuation(self):
        """纯标点符号返回空列表"""
        assert tokenize("!@#$%^&*()") == []

    def test_tokenizer_numbers(self):
        """数字保留"""
        words = tokenize("test123")
        assert "test123" in words

    def test_tokenizer_mixed_case(self):
        """英文转小写"""
        words = tokenize("Hello World")
        assert "hello" in words
        assert "world" in words
        assert "Hello" not in words
