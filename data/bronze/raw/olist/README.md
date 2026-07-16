# Olist E-Commerce Source Dataset

## Dataset

Brazilian E-Commerce Public Dataset by Olist.

## Purpose

The dataset provides the real transactional foundation for the MSc research project:

**Design and Evaluation of Policy-as-Code Gates with Bounded Self-Healing for Cloud-Native Data Pipeline CI/CD**

## Expected Source Files

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

## Repository Policy

The raw CSV files are intentionally excluded from Git because they are external source data and include large files.

The repository tracks:

- source documentation;
- profiling code;
- source profiling results;
- transformation logic;
- governance metadata;
- dataset contracts;
- validation logic;
- Policy-as-Code rules;
- Infrastructure-as-Code;
- CI/CD workflows;
- experiment definitions and research evidence.

The cloud implementation will store the source data in the Amazon S3 bronze layer.

## Reproducibility

Source profiling results are stored under:

`data/profile/`

The profiling script is stored at:

`scripts/profile_source_data.py`
