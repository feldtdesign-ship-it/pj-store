#!/bin/sh
# fetch_data.sh — refresh the product data the preview is built from (public feeds on pjorourkeii.com).
cd "$(dirname "$0")/data" || exit 1
curl -sL "https://pjorourkeii.com/products.json?limit=250&page=1" -o products-p1.json
curl -sL "https://pjorourkeii.com/products.json?limit=250&page=2" -o products-p2.json
curl -sL "https://pjorourkeii.com/collections.json?limit=250" -o collections.json
for h in signed-unsigned signed-unsigned-1 prints-1 new-prints screen-prints post-cards heat-transfer-tees buttery-soft-tees cement-gray-tees crop-tees hats-buckets beanies jackets-coats jackets hoodie crewnecks featured-2 artists-choice; do
  curl -sL "https://pjorourkeii.com/collections/$h/products.json?limit=250" -o "coll-$h.json"
done
ls -la
