# Model weights

Local model files for StaX's offline AI discovery (EP7). Everything here runs on
CPU via `onnxruntime`; **no cloud/API is ever used**.

## `clip-vit-b32-onnx/`

OpenAI **CLIP ViT-B/32**, used for semantic (text), visual (image),
find-similar, and auto-tag search.

| File | What | Source |
|---|---|---|
| `clip_image.onnx` | Image encoder, uint8-quantized. Input `(1,3,224,224)` float32 → `(1,512)` | [josephrocca/openai-clip-js](https://huggingface.co/rocca/openai-clip-js) |
| `clip_text.onnx` | Text encoder, uint8-quantized. Input `(1,77)` int32 token ids → `(1,512)` | [josephrocca/openai-clip-js](https://huggingface.co/rocca/openai-clip-js) |
| `bpe_simple_vocab_16e6.txt.gz` | CLIP BPE merge table for the tokenizer | [openai/CLIP](https://github.com/openai/CLIP) (MIT) |

The tokenizer that reads the vocab is vendored at [`clip_tokenizer.py`](../clip_tokenizer.py)
(adapted from OpenAI CLIP, MIT). CLIP is released by OpenAI under the MIT License.

## (Re)fetching

These files are fetched (and SHA-256 verified) by:

```bash
python -m tools.download_clip_model
```

Re-running skips files already present with a matching checksum. The download
target is `weights/clip-vit-b32-onnx/` by default; override with the
`STAX_AI_MODEL_DIR` environment variable.

## Swapping the model

Replace the two `.onnx` files (and the vocab if the tokenization changes),
keeping the same input/output contract above, or point `STAX_AI_MODEL_DIR` at a
different folder. `src/ai/embedder.py::ClipOnnxEmbedder` reads
`clip_image.onnx` / `clip_text.onnx` from the model dir.
