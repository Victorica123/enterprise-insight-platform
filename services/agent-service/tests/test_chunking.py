"""A4 回归测试：结构感知切块（标题层级链、句子边界、超长句硬切）。

历史教训：flush() 未重置缓冲导致所有章节块内容相同；标题进了 title 没进检索词。
这些用例把两个坑都钉住。
"""
import unittest

from app.rag import split_text


class ChunkingTests(unittest.TestCase):
    def test_heading_hierarchy_becomes_chunk_titles(self) -> None:
        text = "# 运维手册\n\n## 工单分级\nP0响应时限30分钟。\n\n## 超时升级\n超时自动升级。"
        chunks = split_text(text)
        titles = {title for title, _content in chunks}
        self.assertIn("运维手册 / 工单分级", titles)
        self.assertIn("运维手册 / 超时升级", titles)
        p0 = next(content for title, content in chunks if "工单分级" in title)
        self.assertIn("响应时限30分钟", p0)
        self.assertNotIn("超时自动升级", p0)

    def test_each_section_chunk_contains_only_its_own_content(self) -> None:
        text = "# 文档\n\n## A\n第一节内容。\n\n## B\n第二节内容。\n\n## C\n第三节内容。"
        chunks = split_text(text)
        contents = {title: content for title, content in chunks}
        for title, content in contents.items():
            section = title.split("/")[-1].strip()
            if section == "A":
                self.assertEqual(content, "第一节内容。")
            elif section == "B":
                self.assertEqual(content, "第二节内容。")
            elif section == "C":
                self.assertEqual(content, "第三节内容。")

    def test_no_heading_returns_empty_title(self) -> None:
        chunks = split_text("第一句。第二句。")
        self.assertTrue(chunks)
        self.assertTrue(all(title == "" for title, _content in chunks))

    def test_sentence_boundaries_never_split_mid_sentence(self) -> None:
        sentences = [f"第{index}句内容测试数据填充。" for index in range(80)]
        chunks = split_text("\n".join(sentences))
        self.assertGreater(len(chunks), 1)
        for _title, content in chunks:
            for line in content.split("\n"):
                self.assertTrue(line.endswith("。"))

    def test_oversized_sentence_is_hard_split_with_title(self) -> None:
        long_sentence = "延期原因是" + "测试环境部署失败" * 80 + "。"
        chunks = split_text("# 记录\n" + long_sentence)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(title == "记录" for title, _content in chunks))
        self.assertTrue(all(len(content) <= 600 for _title, content in chunks))


if __name__ == "__main__":
    unittest.main()
