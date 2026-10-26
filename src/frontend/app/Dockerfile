FROM nginx:1.25-alpine

COPY ./index.html /usr/share/nginx/html/index.html
COPY ./styles.css /usr/share/nginx/html/styles.css
COPY ./app.js /usr/share/nginx/html/app.js

COPY ./default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
