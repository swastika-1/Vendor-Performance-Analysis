import sqlite3
import pandas as pd
import logging
from ingestion_db import ingest_db

# Configure logging
import os

os.makedirs("logs", exist_ok=True)

log_path = os.path.abspath("logs/get_vendor_summary.log")

logging.basicConfig(
    filename=log_path,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a",
    force=True
)

logging.info("Vendor summary logging started")


def create_vendor_summary(conn):
    """Merge different tables to create the overall vendor summary."""

    vendor_sales_summary = pd.read_sql_query(
        """
        WITH FreightSummary AS (
            SELECT
                VendorNumber,
                SUM(Freight) AS FreightCost
            FROM vendor_invoice
            GROUP BY VendorNumber
        ),

        PurchaseSummary AS (
            SELECT
                p.VendorNumber,
                p.VendorName,
                p.Brand,
                p.Description,
                p.PurchasePrice,
                pp.Price AS ActualPrice,
                pp.Volume,
                SUM(p.Quantity) AS TotalPurchaseQuantity,
                SUM(p.Dollars) AS TotalPurchaseDollars
            FROM purchases p
            JOIN purchase_prices pp
                ON p.Brand = pp.Brand
            WHERE p.PurchasePrice > 0
            GROUP BY
                p.VendorNumber,
                p.VendorName,
                p.Brand,
                p.Description,
                p.PurchasePrice,
                pp.Price,
                pp.Volume
        ),

        SalesSummary AS (
            SELECT
                VendorNo,
                Brand,
                SUM(SalesQuantity) AS TotalSalesQuantity,
                SUM(SalesDollars) AS TotalSalesDollars,
                SUM(SalesPrice) AS TotalSalesPrice,
                SUM(ExciseTax) AS TotalExciseTax
            FROM sales
            GROUP BY VendorNo, Brand
        )

        SELECT
            ps.VendorNumber,
            ps.VendorName,
            ps.Brand,
            ps.Description,
            ps.PurchasePrice,
            ps.ActualPrice,
            ps.Volume,
            ps.TotalPurchaseQuantity,
            ps.TotalPurchaseDollars,
            ss.TotalSalesQuantity,
            ss.TotalSalesDollars,
            ss.TotalSalesPrice,
            ss.TotalExciseTax,
            fs.FreightCost
        FROM PurchaseSummary ps
        LEFT JOIN SalesSummary ss
            ON ps.VendorNumber = ss.VendorNo
            AND ps.Brand = ss.Brand
        LEFT JOIN FreightSummary fs
            ON ps.VendorNumber = fs.VendorNumber
        ORDER BY ps.TotalPurchaseDollars DESC
        """,
        conn
    )

    return vendor_sales_summary


def clean_data(df):
    """This function will clean the data."""

    # Changing datatype to float
    df["Volume"] = df["Volume"].astype(float)

    # Filling missing values with 0
    df.fillna(0, inplace=True)

    # Removing spaces from categorical columns
    df["VendorName"] = df["VendorName"].str.strip()
    df["Description"] = df["Description"].str.strip()

    # Creating new columns for better analysis
    df["GrossProfit"] = (
        df["TotalSalesDollars"] - df["TotalPurchaseDollars"]
    )

    df["ProfitMargin"] = (
        df["GrossProfit"] / df["TotalSalesDollars"]
    ) * 100

    df["StockTurnover"] = (
        df["TotalSalesQuantity"] / df["TotalPurchaseQuantity"]
    )

    df["SalesToPurchaseRatio"] = (
        df["TotalSalesDollars"] / df["TotalPurchaseDollars"]
    )

    return df


if __name__ == "__main__":

    # Creating database connection
    conn = sqlite3.connect("inventory.db")

    try:
        logging.info("Creating Vendor Summary Table.....")
        summary_df = create_vendor_summary(conn)
        logging.info("\n%s", summary_df.head())

        logging.info("Cleaning Data.....")
        clean_df = clean_data(summary_df)
        logging.info("\n%s", clean_df.head())

        logging.info("Ingesting Data.....")
        ingest_db(clean_df, "vendor_sales_summary", conn)

        logging.info("Completed")

    except Exception:
        logging.exception("An error occurred while creating vendor summary")

    finally:
        conn.close()