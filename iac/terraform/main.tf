terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

# Buckets
resource "aws_s3_bucket" "boveda" {
  bucket = var.bucket_boveda
}
resource "aws_s3_bucket" "exports" {
  bucket = var.bucket_exports
}

# Role para Lambda
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service", identifiers = ["lambda.amazonaws.com"] }
  }
}
resource "aws_iam_role" "lambda_exec" {
  name               = "${var.prefix}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Políticas
data "aws_iam_policy_document" "policy" {
  statement {
    sid     = "CloudWatchLogs"
    actions = ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"]
    resources = ["*"]
  }
  statement {
    sid     = "S3BovedaRead"
    actions = ["s3:ListBucket"]
    resources = [aws_s3_bucket.boveda.arn]
  }
  statement {
    sid     = "S3BovedaGet"
    actions = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.boveda.arn}/extract/*"]
  }
  statement {
    sid     = "S3ExportsRW"
    actions = ["s3:GetObject","s3:PutObject","s3:ListBucket"]
    resources = [aws_s3_bucket.exports.arn, "${aws_s3_bucket.exports.arn}/*"]
  }
}
resource "aws_iam_policy" "lambda_policy" {
  name   = "${var.prefix}-lambda-policy"
  policy = data.aws_iam_policy_document.policy.json
}
resource "aws_iam_role_policy_attachment" "attach" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# Lambda R8
resource "aws_lambda_function" "r8_excel" {
  function_name = "${var.prefix}-r8-excel"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "src/lambdas/r8_excel_handler.handler"
  runtime       = "python3.11"
  filename      = var.r8_zip
  source_code_hash = filebase64sha256(var.r8_zip)

  environment {
    variables = {
      BUCKET_BOVEDA  = var.bucket_boveda
      BUCKET_EXPORTS = var.bucket_exports
    }
  }
  timeout = 900
  memory_size = 1024
}

# Lambda R9
resource "aws_lambda_function" "r9_word" {
  function_name = "${var.prefix}-r9-word"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "src/lambdas/r9_word_handler.handler"
  runtime       = "python3.11"
  filename      = var.r9_zip
  source_code_hash = filebase64sha256(var.r9_zip)

  environment {
    variables = {
      BUCKET_EXPORTS = var.bucket_exports
    }
  }
  timeout = 900
  memory_size = 1024
}
