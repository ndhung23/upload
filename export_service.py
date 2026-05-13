from io import BytesIO

import pandas as pd

from models import (
    DimCarMaker,
    DimCountry,
    DimCountryOfMaker,
    DimCustomer,
    DimLaser,
    DimMarket,
    DimType,
    DimType2,
    FactETD,
)


def _records(query, columns):
    return [{column: getattr(row, column) for column in columns} for row in query.all()]


def build_export_workbook():
    output = BytesIO()

    sheets = {
        "FACT_ETD": (
            FactETD.query.order_by(FactETD.PartNo, FactETD.Month),
            [
                "PartNo",
                "CustomerID",
                "TypeID",
                "LaserID",
                "CountryOfMakerID",
                "CarMakerID",
                "CountryID",
                "MarketID",
                "Type2ID",
                "Month",
                "Value",
            ],
        ),
        "DIM_Customer": (DimCustomer.query.order_by(DimCustomer.CustomerID), ["CustomerID", "Customer"]),
        "DIM_Type": (DimType.query.order_by(DimType.TypeID), ["TypeID", "Type"]),
        "DIM_Laser": (DimLaser.query.order_by(DimLaser.LaserID), ["LaserID", "Laser"]),
        "DIM_CountryOfMaker": (
            DimCountryOfMaker.query.order_by(DimCountryOfMaker.CountryOfMakerID),
            ["CountryOfMakerID", "CountryOfMaker"],
        ),
        "DIM_CarMaker": (DimCarMaker.query.order_by(DimCarMaker.CarMakerID), ["CarMakerID", "CarMaker"]),
        "DIM_Country": (DimCountry.query.order_by(DimCountry.CountryID), ["CountryID", "Country"]),
        "DIM_Market": (DimMarket.query.order_by(DimMarket.MarketID), ["MarketID", "Market"]),
        "DIM_Type2": (DimType2.query.order_by(DimType2.Type2ID), ["Type2ID", "Type2"]),
    }

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, (query, columns) in sheets.items():
            pd.DataFrame(_records(query, columns), columns=columns).to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )

    output.seek(0)
    return output
