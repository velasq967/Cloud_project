FROM nginx:1.25-alpine

COPY services/frontend/app/index.html /usr/share/nginx/html/index.html
COPY services/frontend/app/styles.css /usr/share/nginx/html/styles.css
COPY services/frontend/app/app.js /usr/share/nginx/html/app.js

COPY services/frontend/app/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
