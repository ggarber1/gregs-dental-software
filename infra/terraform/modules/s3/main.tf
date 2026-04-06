locals {
  buckets = {
    phi_documents = "dental-phi-documents-${var.env}"
    era_files     = "dental-era-files-${var.env}"
    exports       = "dental-exports-${var.env}"
  }
}

resource "aws_s3_bucket" "phi_documents" {
  bucket = local.buckets.phi_documents
  tags   = merge(var.tags, { Name = local.buckets.phi_documents, DataClass = "PHI" })
}

resource "aws_s3_bucket" "era_files" {
  bucket = local.buckets.era_files
  tags   = merge(var.tags, { Name = local.buckets.era_files, DataClass = "PHI" })
}

resource "aws_s3_bucket" "exports" {
  bucket = local.buckets.exports
  tags   = merge(var.tags, { Name = local.buckets.exports })
}

# Static map with known keys — for_each requires keys determinable at plan time
locals {
  bucket_map = {
    phi_documents = aws_s3_bucket.phi_documents.id
    era_files     = aws_s3_bucket.era_files.id
    exports       = aws_s3_bucket.exports.id
  }
}

resource "aws_s3_bucket_versioning" "main" {
  for_each = local.bucket_map
  bucket   = each.value

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  for_each = local.bucket_map
  bucket   = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  for_each = local.bucket_map
  bucket   = each.value

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# PHI documents: 7-year HIPAA retention, transition to IA after 90 days
resource "aws_s3_bucket_lifecycle_configuration" "phi_documents" {
  bucket = aws_s3_bucket.phi_documents.id

  rule {
    id     = "phi-lifecycle"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 2557 # 7 years
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# ERA files: 7-year retention (insurance audit requirements)
resource "aws_s3_bucket_lifecycle_configuration" "era_files" {
  bucket = aws_s3_bucket.era_files.id

  rule {
    id     = "era-lifecycle"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 2557
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# Exports: 90-day expiry (transient reports)
resource "aws_s3_bucket_lifecycle_configuration" "exports" {
  bucket = aws_s3_bucket.exports.id

  rule {
    id     = "exports-lifecycle"
    status = "Enabled"

    filter {}

    expiration {
      days = 90
    }
  }
}
