# Copy-Paste cURL Commands for Evaluators

You can execute these terminal commands sequentially to demonstrate the complete workflow of the service.

---

## 1. Set Base URL

```bash
export BASE_URL="http://localhost:8000"
```

---

## 2. Check System Health

```bash
curl -s -X GET "$BASE_URL/health" | jq .
curl -s -X GET "$BASE_URL/health/ready" | jq .
```

---

## 3. Register & Authenticate

```bash
# Register an evaluator account
curl -s -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "evaluator@example.com",
    "password": "EvaluatorPassword123!"
  }' | jq .

# Login and capture JWT Bearer Token
export TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "evaluator@example.com",
    "password": "EvaluatorPassword123!"
  }' | jq -r '.access_token')

echo "Acquired Bearer Token: $TOKEN"
```

---

## 4. Verify Identity

```bash
curl -s -X GET "$BASE_URL/api/v1/auth/me" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 5. Upload Examination Paper

```bash
# Upload digital exam PDF and capture Document ID
export DOC_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/documents/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@samples/demo/digital_exam.pdf" \
  -F "document_role=QUESTION_PAPER")

echo $DOC_RESPONSE | jq .
export DOCUMENT_ID=$(echo $DOC_RESPONSE | jq -r '.id')
echo "Document ID: $DOCUMENT_ID"
```

---

## 6. Poll Processing Status

```bash
# Check processing telemetry
curl -s -X GET "$BASE_URL/api/v1/documents/$DOCUMENT_ID/status" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 7. Inspect Extracted Questions

```bash
# Retrieve paginated list of extracted questions
curl -s -X GET "$BASE_URL/api/v1/documents/$DOCUMENT_ID/questions?page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Capture the first question's ID
export QUESTION_ID=$(curl -s -X GET "$BASE_URL/api/v1/documents/$DOCUMENT_ID/questions" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')

echo "Question ID: $QUESTION_ID"
```

---

## 8. View Question Details & Bounding Boxes

```bash
curl -s -X GET "$BASE_URL/api/v1/questions/$QUESTION_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 9. Upload & Associate Answer Key

```bash
# Upload the answer key PDF
export KEY_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/documents/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@samples/demo/answer_key.pdf" \
  -F "document_role=ANSWER_KEY")

export ANSWER_KEY_ID=$(echo $KEY_RESPONSE | jq -r '.id')
echo "Answer Key Document ID: $ANSWER_KEY_ID"

# Link answer key to question paper
curl -s -X POST "$BASE_URL/api/v1/documents/$DOCUMENT_ID/related" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"related_document_id\": \"$ANSWER_KEY_ID\",
    \"relationship_type\": \"ANSWER_KEY\"
  }" | jq .

# View answer mappings
curl -s -X GET "$BASE_URL/api/v1/documents/$DOCUMENT_ID/answer-mappings" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 10. Inspect Human Review Queue & Resolve Item

```bash
# View review items for document
curl -s -X GET "$BASE_URL/api/v1/documents/$DOCUMENT_ID/reviews" \
  -H "Authorization: Bearer $TOKEN" | jq .

# If items exist, resolve with:
# export REVIEW_ID="<item-uuid>"
# curl -s -X PATCH "$BASE_URL/api/v1/reviews/$REVIEW_ID" \
#   -H "Authorization: Bearer $TOKEN" \
#   -H "Content-Type: application/json" \
#   -d '{"status": "RESOLVED", "notes": "Reviewed and confirmed by evaluator."}' | jq .
```

---

## 11. Test File Validation Security Guards

```bash
# Attempt to upload an invalid/forbidden file type (.txt or .exe)
curl -s -i -X POST "$BASE_URL/api/v1/documents/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@README.md"
```
*(Notice the immediate `400 Bad Request` or validation error rejection).*
