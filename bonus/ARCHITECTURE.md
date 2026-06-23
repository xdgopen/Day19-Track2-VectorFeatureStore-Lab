# Hybrid Memory POC — Nguyễn Danh Thành (2A202600581)

## Mục tiêu và kiến trúc

POC là trợ lý cá nhân tiếng Việt có hai loại trí nhớ. Episodic memory là nội dung hội thoại, ghi chú và tài liệu vừa đọc; nó phải tìm được theo ý nghĩa lẫn từ khóa. Stable profile là các thuộc tính ít đổi như ngôn ngữ, tốc độ đọc và lĩnh vực quan tâm; recent activity là tín hiệu ngắn hạn như số query trong một giờ. Tôi dùng Qdrant in-memory cho demo và Feast local (Parquet offline + SQLite online) để giữ POC chạy được trên laptop, nhưng interface tương thích với Qdrant server/Redis ở production.

```text
                    remember(text, user_id)
                             |
              sentence-aware chunking (<= 500 chars)
                             |
                 FastEmbed multilingual-ish embedding
                             v
        +------------------------------------------+
        | Qdrant episodic collection               |
        | vector + {user_id, text, created_at}     |
        +------------------------------------------+

 profile batch daily ----> Parquet ----> Feast materialize ---> SQLite/Redis
 recent events stream ---> Push/source ----^             |
                                                        v
recall(query, user_id) --> Feast online features + Qdrant semantic search
                         + BM25 lexical search --> RRF (k=60)
                                                        |
                                                        v
             assembled personalized context --> LLM final response (outside POC)
```

Luồng `recall` luôn filter Qdrant bằng `user_id`, sau đó lấy top-10 semantic và toàn bộ lexical candidates của riêng user đó. Reciprocal Rank Fusion cộng `1/(60 + rank)` với rank bắt đầu từ 1, chọn top-3 memories. Cuối cùng agent ghép chúng với online features thành context có thể gửi cho LLM. POC không gọi LLM thật: điều này cô lập và làm rõ phần retrieval/personalization cần đánh giá.

## Quyết định 1 — chunking episodic memory

Tôi chọn chunk theo câu, gộp tối đa khoảng 500 ký tự (xấp xỉ 100–150 token tiếng Việt), và lưu từng chunk cùng `user_id`. Một tin nhắn ngắn được giữ nguyên; một ghi chú dài được tách ở ranh giới câu trước khi fallback sang cắt độ dài. So với **một vector cho cả conversation**, chunk nhỏ tăng retrieval precision: query về HPA không bị chìm trong một cuộc nói chuyện dài về Kubernetes. Nó cũng giúp đưa đúng vài đoạn vào context window thay vì nhét cả hội thoại.

Tradeoff là storage và embedding cost tăng theo số chunk; quá nhỏ thì mất quan hệ giữa các câu, quá lớn thì có nhiều noise và tốn context window. Với POC nhỏ, 500 ký tự là điểm cân bằng thiên về recall chính xác. Production có thể dùng semantic splitter 200–350 tokens, overlap 10–15%, metadata `conversation_id`, timestamp và source URL. Tôi không chọn overlap lớn mặc định vì tin nhắn tiếng Việt thường ngắn, duplication sẽ làm RRF ưu ái cùng một ý và tăng chi phí index.

## Quyết định 2 — schema feature store

Tôi chọn **tabular features trước**, gồm entity `user_id`: `reading_speed_wpm` (Int64, TTL 30 ngày, batch profile), `preferred_language` (String, 30 ngày), `topic_affinity` (String, 30 ngày), `queries_last_hour` (Int64, TTL 1 giờ, streaming) và `distinct_topics_24h` (Int64, TTL 1 giờ). Vì item popularity là một concern độc lập, entity `doc_id` giữ `click_count_24h`, `ctr_7d`, `avg_dwell_seconds` để sau này rerank recommendation.

Tradeoff là tabular schema dễ inspect, PIT join và debug, nên phù hợp cold start và POC; nhưng `topic_affinity="cloud"` không diễn tả được preference đa chiều hoặc thay đổi tinh tế. Embedding profile latent từ lịch sử có thể cá nhân hóa tốt hơn, nhưng khó explain, cần re-embed khi model đổi và gây rủi ro privacy khi history quá ít. Vì vậy tôi **đã cân nhắc lưu episodic embeddings trong Feast**, nhưng loại bỏ: lifecycle của memories tính theo phút/giờ, còn feature registry/materialization thích hợp với stable, typed, point-in-time features. Vector store là nơi đúng cho retrieval; Feast là nơi đúng cho serving-consistent profile.

## Quyết định 3 — freshness theo use case

Không có một SLA freshness đúng cho mọi dữ liệu. (1) Khi user lưu một ghi chú hoặc vừa đọc tài liệu và ngay lập tức hỏi “trợ lý nhớ gì về tôi?”, episodic memory phải upsert Qdrant đồng bộ trước khi trả HTTP response: mục tiêu dưới một giây. (2) `queries_last_hour` phục vụ phát hiện interest/fatigue và recommendation; stream/Feast Push source mục tiêu 30–60 giây là đủ, vì query tiếp theo không cần nhìn thấy click vài mili-giây trước. (3) `topic_affinity`, ngôn ngữ và tốc độ đọc chỉ cần batch hằng ngày hoặc khi user chỉnh settings; refresh quá nhanh tạo churn và khiến recommendation dao động.

Tradeoff streaming sub-second là infrastructure cost, duplicate/out-of-order events và khó observability; batch 5 phút rẻ hơn nhưng làm “gần đây” thành lời hứa sai. TTL 1 giờ trên query velocity tự xóa tín hiệu cũ, còn TTL 30 ngày trên profile ngăn profile stale nhưng không buộc phải recompute mỗi giờ.

## Vietnamese-context và privacy

Vietnamese user thường code-switch “Kubernetes autoscaling”, bỏ dấu hoặc gõ kiểu phonetic. Whitespace BM25 rất minh bạch và tốt cho technical tokens, nhưng tách sai từ ghép như “đám mây”; vector retrieval bù semantic mismatch. Production nên A/B test pyvi/underthesea against whitespace, normalize Unicode/dấu có kiểm soát và dùng embedding multilingual như bge-m3. Tôi tránh tự động “sửa” từ tiếng Anh/tên sản phẩm vì có thể hỏng chính xác lexical search.

Memory là dữ liệu cá nhân. Payload filter `user_id` là hàng rào retrieval đầu tiên, không phải security boundary duy nhất: production cần authorization trước query, encryption at rest/in transit, audit, export/delete và consent theo Nghị định 13/2023/NĐ-CP. Không đưa raw memory vào logs hoặc feature values.

## What this POC does not handle yet

POC chưa có auth thực, encryption, delete/expiry của từng memory, multi-device conflict resolution, persistent Qdrant, event deduplication hay LLM safety/prompt-injection filtering. It also uses a small English-centric embedding model for laptop compatibility; quality tiếng Việt không phải benchmark production. Bước kế tiếp hợp lý là Qdrant server + bge-m3, Feast Redis online store, event schema có timestamps, và đánh giá recall/privacy isolation trên nhiều user.
