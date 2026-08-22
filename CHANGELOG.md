# 变更记录

## 2026-08-22

### 修正

- 恢复 API 成功判断为平台实际返回语义：
  `result == "success" or result_val == 0`。
- 更新 `api_client.is_success_response()`，并让 `main.py`、`quick_test.py`、
  `test_api.py`、`matrix_service.py` 统一复用该判断。
- 本地矩阵 Web 接口成功响应同步为：
  `{"result": "success", "result_val": 0}`。
- 前端矩阵页面同步使用 `result === "success" || result_val === 0`
  判断后端切换是否成功。
- 同步文档，移除旧版 `result == "0"` 表示成功的错误描述。

### 正确响应字段说明

| 字段名 | 类型 | 成功时的值 | 失败时的值 | 说明 |
|--------|------|------------|------------|------|
| `result` | 字符串 | `"success"` | 错误说明文本 | 处理结果说明 |
| `result_val` | 数字 | `0` | `1`, `2`, `3` 等 | 处理结果码 |

正确判断方式：

```python
if result.get("result") == "success" or result.get("result_val") == 0:
    print("成功")
else:
    print(f"失败 [code:{result.get('result_val')}]: {result.get('result')}")
```
