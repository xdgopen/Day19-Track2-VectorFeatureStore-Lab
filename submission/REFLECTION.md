# Reflection — Lab 19

**Tên:** Nguyễn Danh Thành
**Mã số sinh viên:** 2A202600581
**Cohort:** 2A
**Path đã chạy:** lite

---

## Câu hỏi (≤ 200 chữ)

> Trên golden set 50 queries, mode nào thắng ở loại query nào (`exact` /
> `paraphrase` / `mixed`), và tại sao? Khi nào bạn **không** dùng hybrid
> (i.e. khi nào pure BM25 hoặc pure vector là lựa chọn đúng)?

Trên 50 golden queries, hybrid RRF có Precision@10 cao nhất: 78.6%, hơn
BM25 77.8% và vector 73.2%. Với `mixed`, hybrid đạt 100% vì kết hợp được
thuật ngữ chính xác và ý nghĩa. Với `exact`, BM25 và hybrid cùng đạt 96.7%:
lexical signal đã đủ mạnh. Ở lite path, BM25 tốt hơn vector trên
`paraphrase` (33.3% so với 24.0%) vì `bge-small-en-v1.5` không tối ưu tiếng
Việt; production nên đánh giá bge-m3/multilingual embedding.

Tôi không dùng hybrid khi latency/cost rất chặt hoặc query là exact
identifier (mã lỗi, SKU, tên API): BM25 đơn giản, dễ giải thích. Pure vector
phù hợp khi embedding multilingual tốt và query hoàn toàn semantic.

---

## Điều ngạc nhiên nhất khi làm lab này

RRF không “chữa” được embedding model không phù hợp ngôn ngữ; nó chỉ làm hệ
thống bền vững hơn khi hai retriever có tín hiệu bổ sung.

---

## Bonus challenge

- [x] Đã làm bonus (xem `bonus/`)
- [ ] Pair work với: _Không có_
