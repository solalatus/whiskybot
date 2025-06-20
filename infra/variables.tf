# variables.tf
variable "aws_region"   { type = string }
variable "domain_name" {
  description = "The public domain for the app"
  type        = string
}
variable "image_tag"    { type = string }
