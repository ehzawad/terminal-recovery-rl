## Data Pipeline: CSV ETL into PostgreSQL

Build a Python ETL pipeline that reads four local CSV input files, validates and cleans the data, joins them into a single denormalized fact table, loads valid rows into a PostgreSQL database, quarantines invalid rows, and produces a JSON summary report.

### Technical Requirements

- Language: Python 3
- Database: PostgreSQL (local instance)
- DB name: `quickviz`, role: `quickviz`, password: `quickviz`, host: `localhost`, port: `5432`
- All scripts must be runnable from `/app`

### Input Files

Place the following four CSV files under `/app/data/`:

**`/app/data/products.csv`**
```
product_id,product_name,product_category,unit_price,margin
P001,Widget A,Electronics,29.99,0.35
P002,Gadget B,Electronics,49.99,0.40
P003,Gizmo C,Home,15.00,0.25
P004,,Home,10.00,0.20
P005,Thingamajig E,Toys,5.99,0.15
```

**`/app/data/customers.csv`**
```
customer_id,customer_email,customer_segment
C001,alice@example.com,Enterprise
C002,bob@example.com,SMB
C003,not-an-email,Enterprise
C004,diana@example.com,Consumer
C005,eve@example.com,
```

**`/app/data/orders.csv`**
```
order_id,order_date,customer_id,discount
1001,2024-01-15,C001,0.10
1002,2024-01-15,C002,0.00
1003,bad-date,C003,0.05
1004,2024-01-16,C004,0.20
1005,2024-01-16,C999,0.00
1006,2024-01-16,C001,-0.10
```

**`/app/data/order_items.csv`**
```
order_id,product_id,quantity
1001,P001,2
1001,P002,1
1002,P003,5
1003,P001,3
1004,P005,10
1005,P002,1
1006,P004,4
1006,P001,0
```

### Database Schema

Create a schema called `analytics` with two tables:

**`analytics.daily_orders_fact`**
| Column | Type |
|---|---|
| order_id | INTEGER |
| order_date | DATE |
| customer_id | TEXT |
| customer_email | TEXT |
| customer_segment | TEXT |
| product_id | TEXT |
| product_name | TEXT |
| product_category | TEXT |
| unit_price | NUMERIC(10,2) |
| quantity | INTEGER |
| discount | NUMERIC(5,2) |
| sales_amount | NUMERIC(12,2) |
| margin | NUMERIC(5,2) |

`sales_amount` is computed as: `unit_price * quantity * (1 - discount)`

**`analytics.quarantine_rows`**
| Column | Type |
|---|---|
| source_file | TEXT |
| row_number | INTEGER |
| error_message | TEXT |
| raw_row_data | TEXT |

### ETL Script: `/app/etl.py`

This script must:

1. Read the four CSV files from `/app/data/`.
2. Validate each row:
   - `product_name` must not be empty.
   - `customer_email` must contain exactly one `@` with a `.` after it.
   - `customer_segment` must not be empty.
   - `order_date` must be a valid date in `YYYY-MM-DD` format.
   - `customer_id` in orders must exist in customers.csv (referential integrity).
   - `discount` must be between 0.0 and 1.0 inclusive.
   - `quantity` must be a positive integer (> 0).
3. Rows that fail any validation go into `analytics.quarantine_rows` with the source file name (e.g., `products.csv`), the 1-based row number within that file (excluding header), the error message, and the full raw row as a comma-separated string.
4. Valid rows are joined across the four files and inserted into `analytics.daily_orders_fact`. A row in the fact table is only created when all four related records (product, customer, order, order_item) are individually valid. If any related record is quarantined, the joined row must not appear in the fact table.
5. Compute `sales_amount` as `unit_price * quantity * (1 - discount)`.
6. All text fields (`product_name`, `product_category`, `customer_segment`) must be stripped of leading/trailing whitespace and stored in title case.

### Monitor Script: `/app/monitor.py`

This script must connect to the database and write a JSON report to `/app/report.json` with the following structure:

```json
{
  "fact_row_count": <int>,
  "quarantine_row_count": <int>,
  "total_sales_amount": <float rounded to 2 decimal places>,
  "quarantined_files": {
    "<source_file>": <count>,
    ...
  }
}
```

- `fact_row_count`: total rows in `analytics.daily_orders_fact`.
- `quarantine_row_count`: total rows in `analytics.quarantine_rows`.
- `total_sales_amount`: sum of `sales_amount` in the fact table, rounded to 2 decimal places.
- `quarantined_files`: a dictionary mapping each `source_file` value to its count of quarantined rows.

### Bootstrap Script: `/app/bootstrap.sh`

A bash script that:
1. Sets up the PostgreSQL database `quickviz` with role `quickviz` (password `quickviz`).
2. Creates the `analytics` schema and both tables.
3. Can be run as: `bash /app/bootstrap.sh`

### Execution Order

```
bash /app/bootstrap.sh
python /app/etl.py
python /app/monitor.py
```

After execution, `/app/report.json` must exist and contain the correct summary.

### Requirements File

Provide `/app/requirements.txt` listing all Python dependencies needed.
