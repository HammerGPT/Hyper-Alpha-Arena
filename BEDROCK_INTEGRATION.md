# AWS Bedrock Integration Guide

This guide explains how to use AWS Bedrock LLM models with Diamonddog trading platform.

## Overview

Diamonddog now supports AWS Bedrock as an AI provider, allowing you to use powerful models like:
- **Qwen3-8B** (`huggingface-reasoning-qwen3-8b`)
- **DeepSeek-R1-Distill-Qwen-32B** (`deepseek-llm-r1-distill-qwen-32b`)
- Any other AWS Bedrock models available in your region

## Prerequisites

1. **AWS Account** with Bedrock access
2. **AWS Credentials** (Access Key ID and Secret Access Key)
3. **Model Access** enabled in AWS Bedrock Console
4. **Python Dependencies** (boto3) installed

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install boto3 and other required packages.

### 2. Run Database Migration

If you have an existing database, run the migration script to add Bedrock support:

```bash
python backend/migrations/add_bedrock_fields.py
```

For fresh installations, the new schema will be created automatically.

### 3. Enable Model Access in AWS Bedrock

1. Go to AWS Console → Amazon Bedrock
2. Navigate to **Model access** in the left sidebar
3. Click **Modify model access** or **Manage model access**
4. Select the models you want to use:
   - Qwen3-8B (huggingface)
   - DeepSeek-R1-Distill-Qwen-32B (deepseek)
5. Click **Save changes** and wait for access to be granted

### 4. Get Your AWS Credentials

You need three pieces of information:

1. **AWS Region** (e.g., `ap-southeast-2` for Sydney, `us-east-1` for N. Virginia)
2. **AWS Access Key ID** (e.g., `AKIAIOSFODNN7EXAMPLE`)
3. **AWS Secret Access Key** (e.g., `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`)

To create AWS credentials:
1. Go to AWS Console → IAM
2. Click **Users** → Select your user
3. Go to **Security credentials** tab
4. Click **Create access key**
5. Select "Application running outside AWS"
6. Save the Access Key ID and Secret Access Key

**Important**: Your IAM user needs the following permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": "*"
        }
    ]
}
```

## Using AWS Bedrock with Trading Accounts

### Create a New Bedrock Account

When creating or updating a trading account, set the following fields:

```json
{
    "name": "Qwen3 Trader",
    "account_type": "AI",
    "provider_type": "bedrock",
    "model": "huggingface-reasoning-qwen3-8b",
    "aws_region": "ap-southeast-2",
    "aws_access_key_id": "YOUR_AWS_ACCESS_KEY_ID",
    "aws_secret_access_key": "YOUR_AWS_SECRET_ACCESS_KEY",
    "initial_capital": 10000.0,
    "auto_trading_enabled": true
}
```

### Available Bedrock Models

#### 1. Qwen3-8B (Reasoning Model)
- **Model ID**: `huggingface-reasoning-qwen3-8b`
- **Provider**: Hugging Face (via AWS Bedrock)
- **Strengths**: Advanced reasoning, math, coding
- **Context Length**: 32,768 tokens (natively), 131,072 with YaRN
- **Best For**: Complex decision-making, logical reasoning

#### 2. DeepSeek-R1-Distill-Qwen-32B
- **Model ID**: `deepseek-llm-r1-distill-qwen-32b`
- **Provider**: DeepSeek (via AWS Bedrock)
- **Strengths**: Excellent reasoning, competitive with o1-mini
- **Context Length**: 32,768 tokens
- **Best For**: Advanced trading strategies, market analysis

### Configuration Parameters

The Bedrock integration uses these optimized settings:

- **Temperature**: 0.6 (recommended for reasoning models)
- **Top P**: 0.95
- **Max Tokens**: 5,000

These settings follow the best practices from the model documentation to ensure optimal performance.

## API Usage

### Create Account with Bedrock

```bash
curl -X POST "http://localhost:8000/api/account/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "DeepSeek Trader",
    "provider_type": "bedrock",
    "model": "deepseek-llm-r1-distill-qwen-32b",
    "aws_region": "ap-southeast-2",
    "aws_access_key_id": "YOUR_KEY",
    "aws_secret_access_key": "YOUR_SECRET",
    "initial_capital": 10000.0
  }'
```

### Update Account to Use Bedrock

```bash
curl -X PUT "http://localhost:8000/api/account/1" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "bedrock",
    "model": "huggingface-reasoning-qwen3-8b",
    "aws_region": "us-east-1",
    "aws_access_key_id": "YOUR_KEY",
    "aws_secret_access_key": "YOUR_SECRET"
  }'
```

### Switch Back to OpenAI

```bash
curl -X PUT "http://localhost:8000/api/account/1" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "openai",
    "model": "gpt-4",
    "base_url": "https://api.openai.com/v1",
    "api_key": "YOUR_OPENAI_KEY"
  }'
```

## Troubleshooting

### Common Issues

#### 1. "Model not found" or 403 Error

**Cause**: Model access not enabled in AWS Bedrock Console

**Solution**:
1. Go to AWS Console → Amazon Bedrock
2. Click "Model access"
3. Enable the models you want to use
4. Wait for approval (usually instant for marketplace models)

#### 2. "Invalid credentials" or 401 Error

**Cause**: Incorrect AWS credentials or insufficient permissions

**Solution**:
1. Verify your Access Key ID and Secret Access Key
2. Check IAM permissions (need `bedrock:InvokeModel` permission)
3. Ensure credentials are not expired

#### 3. "Region not supported" Error

**Cause**: Selected region doesn't support Bedrock

**Solution**:
Use one of these Bedrock-supported regions:
- `us-east-1` (N. Virginia)
- `us-west-2` (Oregon)
- `ap-southeast-1` (Singapore)
- `ap-southeast-2` (Sydney)
- `eu-central-1` (Frankfurt)

#### 4. "Rate limit exceeded" Error

**Cause**: Too many API requests

**Solution**:
- Increase the `trigger_interval` in strategy settings
- Request higher quotas in AWS Service Quotas Console
- Use Provisioned Throughput for high-volume trading

### Enable Debug Logging

To see detailed Bedrock API logs:

```python
import logging
logging.getLogger('backend.services.ai_decision_service').setLevel(logging.DEBUG)
```

## Cost Considerations

AWS Bedrock pricing is based on:
- **Input tokens** (tokens sent in prompts)
- **Output tokens** (tokens in model responses)

Approximate costs (as of January 2025):
- **Qwen3-8B**: ~$0.001 per 1K tokens
- **DeepSeek-R1-Distill-Qwen-32B**: ~$0.003 per 1K tokens

Monitor costs in AWS Cost Explorer → Bedrock.

## Model Selection Guide

| Model | Size | Strengths | Use Case | Cost |
|-------|------|-----------|----------|------|
| **Qwen3-8B** | 8B | Fast reasoning, multi-lingual | Quick decisions, high frequency | Low |
| **DeepSeek-R1-32B** | 32B | Advanced reasoning, accuracy | Complex strategies, analysis | Medium |

## Security Best Practices

1. **Never commit AWS credentials** to version control
2. **Use IAM roles** when running on EC2/ECS instead of hardcoded keys
3. **Rotate credentials** regularly (every 90 days)
4. **Use least privilege** principle - only grant `bedrock:InvokeModel` permission
5. **Enable CloudTrail** logging for audit trails

## Architecture

The Bedrock integration follows this flow:

```
Trading Account (provider_type=bedrock)
    ↓
call_ai_for_decision()
    ↓
_process_bedrock_decision()
    ↓
call_bedrock_for_decision()
    ↓
boto3.client('bedrock-runtime').converse()
    ↓
AWS Bedrock API → Model Inference → Response
    ↓
JSON parsing & decision extraction
    ↓
Execute trade
```

## Additional Resources

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Qwen3 Model Card](https://huggingface.co/Qwen/Qwen3-8B)
- [DeepSeek-R1 Paper](https://arxiv.org/abs/2501.12948)
- [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)

## Support

For issues related to:
- **Bedrock integration**: Open an issue in this repository
- **AWS Bedrock service**: Contact AWS Support
- **Model behavior**: Check model documentation or provider forums

---

**Last Updated**: January 2025
