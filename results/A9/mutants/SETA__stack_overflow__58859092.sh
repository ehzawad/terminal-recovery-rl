#!/bin/bash
cd /home/ubuntu/hostname-project
cat > site.yml <<'EOF'
---
- hosts: all
  gather_facts: false
  vars:
    names: {app01: app-server-01, app02: app-server-02, app03: app-server-03, db01: db-primary-01, db02: db-replica-01}
  tasks:
    - name: out dir
      file: {path: /tmp/hostnames, state: directory}
    - name: record
      copy:
        content: "{{ names[inventory_hostname] }}\n"
        dest: "/tmp/hostnames/{{ inventory_hostname }}.txt"
EOF
rm -rf /tmp/hostnames
ansible-playbook -i inventory site.yml
