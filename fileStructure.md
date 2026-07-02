ChatBot/
├─ app/
│  ├─ main.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ logging.py
│  │  └─ security.py
│  ├─ api/
│  │  ├─ deps.py
│  │  └─ routes/
│  │     ├─ chat.py
│  │     ├─ uploads.py
│  │     ├─ audio.py
│  │     ├─ sessions.py
│  │     └─ health.py
│  ├─ schemas/
│  │  ├─ chat.py
│  │  ├─ upload.py
│  │  ├─ audio.py
│  │  └─ common.py
│  ├─ db/
│  │  ├─ database.py
│  │  ├─ models.py
│  │  └─ repositories/
│  │     ├─ sessions.py
│  │     ├─ messages.py
│  │     ├─ attachments.py
│  │     └─ chunks.py
│  ├─ services/
│  │  ├─ llm/
│  │  │  ├─ base.py
│  │  │  ├─ openrouter.py
│  │  │  ├─ openai_provider.py
│  │  │  └─ gemini_provider.py
│  │  ├─ extraction/
│  │  │  ├─ classifier.py
│  │  │  ├─ pdf_parser.py
│  │  │  ├─ image_parser.py
│  │  │  ├─ ocr.py
│  │  │  ├─ text_cleaner.py
│  │  │  └─ pipeline.py
│  │  ├─ rag/
│  │  │  ├─ chunker.py
│  │  │  ├─ embeddings.py
│  │  │  ├─ vector_store.py
│  │  │  ├─ retriever.py
│  │  │  └─ prompt_builder.py
│  │  ├─ storage/
│  │  │  ├─ local.py
│  │  │  └─ s3.py
│  │  ├─ speech/
│  │  │  ├─ stt.py
│  │  │  └─ tts.py
│  │  └─ jobs/
│  │     ├─ tasks.py
│  │     └─ worker.py
│  ├─ utils/
│  │  ├─ files.py
│  │  ├─ mime.py
│  │  └─ ids.py
│  └─ tests/
│     ├─ test_uploads.py
│     ├─ test_extraction.py
│     ├─ test_chat.py
│     └─ test_rag.py
├─ uploads/
├─ requirements.txt
├─ .env.example
└─ README.md