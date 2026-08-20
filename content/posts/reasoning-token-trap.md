# 推理模型的 Token 陷阱：為什麼「會思考」反而交不出答案

本機 agent 換上推理模型後，最令人困惑的故障之一，不是回答品質變差，也不是工具呼叫失敗，而是：工具都跑完了，檔案卻是空的。

這種問題很容易被誤判。你可能以為是寫檔權限、路徑、skill 指令或 agent loop 出錯；但真正的故障點可能更早：模型把輸出預算耗在推理階段，還沒產生最終回答就結束了。

## 症狀：工具成功，產出卻是空的

典型場景如下：

1. agent 收到一個生產任務，例如產生文章、修改檔案或整理資料。
2. 模型正常規劃步驟。
3. 工具呼叫成功，搜尋、讀檔或查詢都完成。
4. 最後應該輸出正式內容時，agent 卻回傳空字串或 fallback 訊息。
5. 執行器因此建立零位元組檔案，或根本沒有可寫入的內容。

最具誤導性的地方是：**前面的工具步驟看起來全部正常。**

因此，工程師常會優先檢查：

- 工具權限；
- 路徑是否存在；
- 寫檔 API 是否成功；
- Markdown 格式是否造成解析失敗；
- agent 是否漏掉最後一個步驟。

這些檢查都合理，但如果模型使用推理模式，還必須多檢查一件事：**模型是否在產生最終回答之前，就耗盡了可生成的 token。**

在本機 nanobot 0.3.0 的程式碼中，當 agent 已完成工具步驟，卻沒有可交付的最終文字時，runtime 會使用 `I completed the tool steps but couldn't produce a final answer.` 這類 fallback 訊息。這能說明訊息來源，但單憑 fallback 本身，不能判定唯一根因；仍需搭配 API 回應中的 `finish_reason`、token 計數與原始內容診斷。

## 根因：推理內容與最終回答共用生成預算

推理模型的輸出通常可以概念化為兩部分：

```text
reasoning tokens + final answer tokens
```

不同 API 可能把推理內容放在 `reasoning`、`reasoning_content`、`thinking`，或以特殊標記包在 `content` 內。欄位形式雖不同，關鍵問題相同：**推理內容會消耗模型的生成預算。**

假設一次請求允許模型最多生成 8,192 tokens，而模型的內部分配如下：

```text
推理：7,900 tokens
最終回答：292 tokens
```

這次請求仍可能勉強產生一小段回答。但如果推理階段繼續展開：

```text
推理：8,192 tokens
最終回答：0 tokens
```

API 可能回傳：

- 大量 reasoning；
- 空的 `content`；
- `finish_reason: "length"` 或等價的長度終止訊號。

對 agent 而言，模型已產生推理內容，卻沒有留下正式回答的空間。

## 為什麼在 agent 工作流中特別容易發生

一般聊天請求通常只包含一次問答；agent 工作流則會累積：

- system prompt；
- skill 說明；
- 使用者任務；
- 工具 schema；
- 工具回傳內容；
- 多輪 tool call 記錄；
- 模型自己的推理內容；
- 最終回答。

工具完成後，模型還必須把整個狀態重新整合成正式產出。這通常正是推理最密集的階段。

如果任務要求的最終產出本身很長，例如完整文章、程式碼檔或結構化報告，風險更高。模型不只要保留回答空間，還要保留足夠長的回答空間。

## 最容易混淆的兩個限制

這類問題常被籠統稱為「context 不夠」，但至少要區分兩種限制。

### 1. 上下文視窗

上下文視窗限制的是：

```text
輸入 tokens + 已生成 tokens
```

輸入包含 system prompt、歷史對話、工具 schema 與工具結果。視窗太小時，常見症狀包括：

- 請求在送出前就超過限制；
- 舊訊息被截斷；
- 工具結果被裁切；
- 模型遺失前文；
- API 回報 context length 錯誤。

Ollama 現行 FAQ 列出的預設 context window 是 4,096 tokens。可以透過 `OLLAMA_CONTEXT_LENGTH`、Modelfile 的 `num_ctx`，或原生 API 的 `options.num_ctx` 調整。對 agent 工作負載，應明確設定需求值，並以 runtime 的實際配置為準。

### 2. 輸出 token 上限

輸出上限限制的是：

```text
模型本次最多能生成多少 tokens
```

在 OpenAI 相容 API 中，常見參數名稱是：

- `max_tokens`；
- `max_completion_tokens`。

推理模型可能把 reasoning 與最終回答一起計入生成量。於是即使上下文視窗很大，仍可能發生：

```text
輸入放得下
工具結果也放得下
但推理先吃完輸出上限
最終回答仍然是空的
```

因此，即使 context window 很大，final answer 仍可能沒有足夠空間。

## `strip_think()` 只能處理標記，不能解決所有推理欄位

很多 agent 會在輸出前做清理，例如：

```python
content = strip_think(response.content)
```

這類函式通常只負責移除：

```text
<think>...</think>
```

本機 nanobot 0.3.0 的 `nanobot/utils/helpers.py` 中，`strip_think()` 會處理 `<think>`、`<thinking>`、`<thought>`、未閉合標記及部分串流控制標記。

但如果 provider 把推理放在獨立欄位，例如：

```json
{
  "reasoning_content": "...",
  "content": ""
}
```

那麼 `strip_think(response.content)` 沒有內容可清理，也無法把 `reasoning_content` 轉換成最終回答。

即使推理內容放在 `<think>` 標記中，清掉標記也只是隱藏文字，並不會歸還已消耗的 token。

## 設定名稱不等於 provider 實際行為

另一個常見陷阱，是把設定檔中的欄位名稱直接當成 API 保證。

例如設定看起來像：

```json
{
  "reasoningEffort": "none"
}
```

但它是否有效，取決於完整轉換鏈：

```text
設定欄位
→ nanobot provider 轉換
→ LiteLLM 或其他 client 參數
→ OpenAI 相容請求
→ Ollama 相容層
→ 模型模板與模型能力
```

其中任何一層沒有轉送、映射錯誤或不支援該值，設定就可能沒有預期效果。

以目前 Ollama 官方 OpenAI 相容文件為準，`/v1/chat/completions` 的 `reasoning_effort` 支援 `low`、`medium`、`high`、`max` 與 `none`。Ollama 原生 `/api/chat` 使用 `think`；該欄位可為布林值，部分模型也支援強度字串。其他 provider 與模型仍可能使用不同參數或值域。

因此，若目標是停用推理，不要只看設定名稱。應確認：

1. nanobot 是否真的把欄位送進請求；
2. 送出的 JSON 鍵名和值是什麼；
3. Ollama 端點是否支援該參數；
4. 目標模型是否允許停用推理；
5. 回應中是否仍有 `reasoning`、`reasoning_content` 或 `thinking`。

在本機 nanobot 0.3.0 的 `openai_compat_provider.py` 中，Qwen thinking 模型另有 `enable_thinking`／provider-specific `extra_body` 處理。這代表「停用推理」是實作與模型相關行為，不能只靠抽象的 `reasoningEffort: none` 推論。

## 記憶體估算：不能只看參數量

調大 context 或輸出上限會增加資源成本。對本機推論而言，至少要考慮：

- 模型權重；
- KV cache；
- runtime buffer；
- GPU 或 CPU offload；
- 量化格式；
- context length；
- batch size；
- 同時請求數。

只以「參數量 × 每參數位元數」估算，最多只能粗估量化權重下限。例如 9B 模型若以理想化 4-bit 計算，原始權重資料約為：

```text
9,000,000,000 × 4 bits ≈ 4.5 GB
```

但實際模型檔會有量化 metadata、不同 tensor 精度與其他開銷；載入後還要加上 KV cache 和 runtime 配置。因此不能由「9B、4-bit」直接推導出固定的 14 GB VRAM 結論，也不能把 context 調大視為免費。

較可靠的方法是：

1. 用 `ollama show <model>` 確認模型與量化資訊；
2. 用 `ollama ps` 查看實際載入、processor 分配與 context；
3. 在目標 context 下量測 VRAM／RAM；
4. 再逐步增加 `num_ctx` 或輸出上限。

## 如何選擇修法

| 任務狀況 | 優先處理 | 限制 |
|---|---|---|
| 格式化、固定工具流程或長篇輸出 | 停用或降低推理 | 需要確認端點與模型是否支援 |
| 任務需要推理，且硬體仍有容量 | 增加輸出上限 | 容量增加不保證 final answer 取得固定比例 |
| 推理成本高於品質收益 | 對該 process 改用非推理模型 | 需要用同一案例比較品質 |

OpenAI 相容層不保證接受 Ollama 原生 API 的 `think: false`。設定完成後，應比較實際請求與回應，確認 reasoning 確實下降。

## 建議的診斷順序

遇到「工具成功但最後輸出為空」時，依序取得以下證據：

1. 保存原始 provider 回應中的 `content`、reasoning 欄位、終止原因與 token 計數。
2. 核對 client 最後送出的 `max_tokens` 或 `max_completion_tokens`。
3. 用 `OLLAMA_CONTEXT_LENGTH`、`num_ctx` 與 `ollama ps` 確認 runtime 的實際 context。
4. 使用同一個 prompt 比較目前設定與降低推理後的結果。
5. 結果仍不清楚時，移除 agent loop，直接呼叫 provider。

長 reasoning、空 `content` 與長度終止訊號同時出現時，可優先調查生成預算。若降低推理後 `content` 恢復，才能確認控制參數有效。直接呼叫 provider 則能把模型或 provider 問題與 agent runtime 問題分開。

## 可觀測性：不要再讓空回答像寫檔錯誤

生產型 agent 至少應記錄以下欄位：

```json
{
  "model": "...",
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "reasoning_tokens": 0,
  "finish_reason": "...",
  "content_length": 0,
  "tool_call_count": 0
}
```

告警條件可使用 `content_length == 0 AND tool_call_count > 0 AND finish_reason == "length"`。條件成立時，先把事件分類為「疑似生成預算耗盡」。

如果 provider 不提供 reasoning token 數，也可以記錄 reasoning 欄位的字元長度，至少能作為趨勢指標。

另外，agent runtime 應把下列情況分開：

```text
模型回傳空 content
模型請求失敗
工具呼叫失敗
寫檔失敗
```

否則，所有問題最後都會表現成「沒有產出」，使根因難以追蹤。

## 查核來源

- Ollama API：Generate a chat message（`think`、`done_reason`、token 計數欄位）：https://docs.ollama.com/api/chat
- Ollama OpenAI compatibility（OpenAI 相容參數與 reasoning 支援）：https://docs.ollama.com/api/openai-compatibility
- Ollama FAQ（context length 設定與 `ollama ps` 檢查方式）：https://docs.ollama.com/faq
- 本機安裝版本：`nanobot-ai 0.3.0`、`ollama 0.30.6`（查核時以本機指令確認）
- 本機 nanobot 原始碼：`nanobot/utils/helpers.py`（`strip_think()`）、`nanobot/providers/openai_compat_provider.py`（Qwen thinking 與 provider-specific 參數處理）、`nanobot/utils/runtime.py`（空 final answer fallback）
