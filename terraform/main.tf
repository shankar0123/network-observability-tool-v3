terraform {
  required_providers {
    hcloud = {
      source = "hetznercloud/hcloud"
      version = "~> 1.35.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type = string
  sensitive = true
}

variable "server_name" {
  description = "Name of the server"
  type = string
  default = "pop-vm"
}

variable "server_type" {
  description = "Hetzner Cloud server type"
  type = string
  default = "cx11"
}

variable "server_image" {
  description = "Hetzner Cloud server image"
  type = string
  default = "ubuntu-22.04"
}

variable "server_location" {
  description = "Hetzner Cloud server location"
  type = string
  default = "nrt1" # Example: Tokyo
}

variable "ssh_key_name" {
  description = "Name of the SSH key in Hetzner Cloud"
  type = string
  default = "default-ssh-key" # Replace with your SSH key name
}

resource "hcloud_server" "pop_vm" {
  name = var.server_name
  server_type = var.server_type
  image = var.server_image
  location = var.server_location
  ssh_keys = [
    data.hcloud_ssh_key.ssh_key.id,
  ]
}

data "hcloud_ssh_key" "ssh_key" {
  name = var.ssh_key_name
}

output "server_public_ip" {
  value = hcloud_server.pop_vm.ipv4_address
  description = "Public IP address of the POP VM"
}