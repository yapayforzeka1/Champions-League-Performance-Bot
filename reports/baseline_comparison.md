# Taban çizgisi karşılaştırması (2026/27) — İÇ ANALİZ, Telegram'a gönderilmez

Kilitli referanslar (sürüm 1): `home_1_0` (hep ev 1-0), `home_2_1` (hep ev 2-1), `fixed_margin_2_1` (modelin sonucu korunur, skoru 2-1 / 1-2 / 1-1 yapılır).

**Önemli:** Referanslar 3. haftaya kadar olan veriye bakılarak seçildi. Bu haftalar 'gözlenen' (iç-örnek) sayılır; adil test yalnızca sonraki haftalardır.

Karşılaştırma aynı maçlarda yapılır: model, yalnızca geçerli tahmin verdiği maçlarda referansla kıyaslanır. Fark = model ortalaması − referans ortalaması.

## Gözlenen haftalar (iç-örnek) — 49 maç

Tüm maçlarda sabit tahmin ortalamaları: home_1_0 3.06, home_2_1 2.98

### Referans: `home_1_0`

| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |
|---|---:|---:|---:|---:|---:|
| Gemini 3.6 Flash | 15 | 3.87 | 2.93 | +0.93 | [+0.13; +1.87] |
| Groq Qwen 3.6 27B | 16 | 3.75 | 2.88 | +0.88 | [-0.12; +2.00] |
| Groq Qwen 3.8 27B | 33 | 2.79 | 3.15 | -0.36 | [-1.52; +0.79] |
| Cloudflare Clef-omni | 33 | 2.12 | 3.15 | -1.03 | [-2.24; +0.24] |
| Cohere Command A+ | 41 | 3.41 | 3.46 | -0.05 | [-0.39; +0.29] |
| Groq GPT-OSS 120B | 48 | 2.92 | 3.12 | -0.21 | [-1.04; +0.67] |
| Konsensüs | 40 | 3.10 | 3.35 | -0.25 | [-1.10; +0.55] |

### Referans: `home_2_1`

| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |
|---|---:|---:|---:|---:|---:|
| Gemini 3.6 Flash | 15 | 3.87 | 3.20 | +0.67 | [-0.13; +1.60] |
| Groq Qwen 3.6 27B | 16 | 3.75 | 3.12 | +0.62 | [-0.38; +1.75] |
| Groq Qwen 3.8 27B | 33 | 2.79 | 2.91 | -0.12 | [-1.15; +0.91] |
| Cloudflare Clef-omni | 33 | 2.12 | 2.91 | -0.79 | [-1.94; +0.36] |
| Cohere Command A+ | 41 | 3.41 | 3.41 | +0.00 | [-0.34; +0.29] |
| Groq GPT-OSS 120B | 48 | 2.92 | 3.04 | -0.12 | [-0.88; +0.67] |
| Konsensüs | 40 | 3.10 | 3.25 | -0.15 | [-0.85; +0.55] |

### Referans: `fixed_margin_2_1`

| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |
|---|---:|---:|---:|---:|---:|
| Gemini 3.6 Flash | 15 | 3.87 | 4.00 | -0.13 | [-0.93; +0.67] |
| Groq Qwen 3.6 27B | 16 | 3.75 | 3.50 | +0.25 | [+0.00; +0.75] |
| Groq Qwen 3.8 27B | 33 | 2.79 | 2.85 | -0.06 | [-0.42; +0.24] |
| Cloudflare Clef-omni | 33 | 2.12 | 2.30 | -0.18 | [-0.61; +0.24] |
| Cohere Command A+ | 41 | 3.41 | 3.32 | +0.10 | [-0.10; +0.34] |
| Groq GPT-OSS 120B | 48 | 2.92 | 2.96 | -0.04 | [-0.25; +0.17] |

## Dış-örnek (adil test) — 32 maç

Tüm maçlarda sabit tahmin ortalamaları: home_1_0 2.06, home_2_1 2.06

### Referans: `home_1_0`

| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |
|---|---:|---:|---:|---:|---:|
| Gemini 3.6 Flash | 12 | 4.00 | 1.33 | +2.67 | [+1.33; +4.00] |
| Gemini 3.5 Flash-Lite | 11 | 4.00 | 2.73 | +1.27 | [-1.45; +3.64] |
| Groq Qwen 3.8 27B | 32 | 3.50 | 2.06 | +1.44 | [+0.06; +2.69] |
| Cloudflare Clef-omni | 32 | 3.00 | 2.06 | +0.94 | [-0.56; +2.38] |
| Cohere Command A+ | 30 | 2.53 | 2.20 | +0.33 | [-0.67; +1.27] |
| Groq GPT-OSS 120B | 30 | 3.40 | 1.87 | +1.53 | [+0.07; +3.00] |
| Konsensüs | 29 | 3.17 | 1.66 | +1.52 | [+0.28; +2.69] |

### Referans: `home_2_1`

| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |
|---|---:|---:|---:|---:|---:|
| Gemini 3.6 Flash | 12 | 4.00 | 1.33 | +2.67 | [+1.33; +4.00] |
| Gemini 3.5 Flash-Lite | 11 | 4.00 | 2.73 | +1.27 | [-1.27; +3.64] |
| Groq Qwen 3.8 27B | 32 | 3.50 | 2.06 | +1.44 | [+0.06; +2.75] |
| Cloudflare Clef-omni | 32 | 3.00 | 2.06 | +0.94 | [-0.62; +2.38] |
| Cohere Command A+ | 30 | 2.53 | 2.20 | +0.33 | [-0.67; +1.27] |
| Groq GPT-OSS 120B | 30 | 3.40 | 1.80 | +1.60 | [+0.07; +3.07] |
| Konsensüs | 29 | 3.17 | 1.66 | +1.52 | [+0.28; +2.69] |

### Referans: `fixed_margin_2_1`

| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |
|---|---:|---:|---:|---:|---:|
| Gemini 3.6 Flash | 12 | 4.00 | 4.50 | -0.50 | [-1.17; +0.00] |
| Gemini 3.5 Flash-Lite | 11 | 4.00 | 3.27 | +0.73 | [+0.00; +1.82] |
| Groq Qwen 3.8 27B | 32 | 3.50 | 3.38 | +0.12 | [-0.31; +0.62] |
| Cloudflare Clef-omni | 32 | 3.00 | 3.00 | +0.00 | [-0.50; +0.50] |
| Cohere Command A+ | 30 | 2.53 | 2.67 | -0.13 | [-0.33; +0.00] |
| Groq GPT-OSS 120B | 30 | 3.40 | 3.47 | -0.07 | [-0.60; +0.47] |
