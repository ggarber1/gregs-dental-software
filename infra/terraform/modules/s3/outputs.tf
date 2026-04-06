output "phi_documents_bucket" {
  value = aws_s3_bucket.phi_documents.id
}

output "phi_documents_bucket_arn" {
  value = aws_s3_bucket.phi_documents.arn
}

output "era_files_bucket" {
  value = aws_s3_bucket.era_files.id
}

output "era_files_bucket_arn" {
  value = aws_s3_bucket.era_files.arn
}

output "exports_bucket" {
  value = aws_s3_bucket.exports.id
}

output "exports_bucket_arn" {
  value = aws_s3_bucket.exports.arn
}
