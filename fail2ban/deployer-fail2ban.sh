#!/bin/bash
scp fail2ban-filter-meta-abuse.conf root@infosaone.com:/etc/fail2ban/filter.d/nginx-meta-abuse.conf
scp fail2ban-filter-scanner.conf root@infosaone.com:/etc/fail2ban/filter.d/nginx-scanner.conf
scp fail2ban-nginx-bad-bots.conf root@infosaone.com:/etc/fail2ban/filter.d/nginx-bad-bots.conf
scp fail2ban-jail-nginx-bad-bots.conf root@infosaone.com:/etc/fail2ban/jail.d/nginx-bad-bots.conf
ssh root@infosaone.com 'systemctl stop fail2ban'
ssh root@infosaone.com 'systemctl start fail2ban'
ssh root@infosaone.com 'systemctl status fail2ban'
ssh root@infosaone.com 'fail2ban-client status'
ssh root@infosaone.com 'fail2ban-client status nginx-meta-abuse'
ssh root@infosaone.com 'fail2ban-client status nginx-bad-bots'
ssh root@infosaone.com 'fail2ban-client status nginx-scanner'


