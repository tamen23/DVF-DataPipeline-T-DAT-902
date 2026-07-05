#!/bin/bash
# Homepedia - Pipeline de données complète
# Usage: ./pipeline.sh [year]

YEAR=${1:-2023}
PREV_YEAR=$((YEAR - 1))

echo ""
echo "========================================"
echo "  HOMEPEDIA - Pipeline de données"
echo "  Année: $YEAR (YoY depuis $PREV_YEAR)"
echo "========================================"
echo ""

set -e  # Stop on error

echo "[1/8] Téléchargement des communes..."
python -m data_pipeline.ingestion.ingest_communes

echo ""
echo "[2/8] Téléchargement ARCEP..."
python -m data_pipeline.ingestion.ingest_arcep

echo ""
echo "[3/8] Téléchargement DVF $PREV_YEAR (pour calcul YoY)..."
python -m data_pipeline.ingestion.ingest_dvf --year $PREV_YEAR

echo ""
echo "[4/8] Téléchargement DVF $YEAR..."
python -m data_pipeline.ingestion.ingest_dvf --year $YEAR

echo ""
echo "[5/8] Bronze + Silver DVF $PREV_YEAR..."
python -m data_pipeline.transformation.bronze_dvf --year $PREV_YEAR
python -m data_pipeline.cleaning.silver_dvf --year $PREV_YEAR
python -m data_pipeline.transformation.gold_real_estate --year $PREV_YEAR

echo ""
echo "[6/8] Bronze + Silver DVF $YEAR..."
python -m data_pipeline.transformation.bronze_dvf --year $YEAR
python -m data_pipeline.cleaning.silver_dvf --year $YEAR
python -m data_pipeline.transformation.gold_real_estate --year $YEAR

echo ""
echo "[7/8] Build Territory Gold $YEAR..."
python -m data_pipeline.transformation.build_territory_gold --year $YEAR

echo ""
echo "[8/8] Upload vers HDFS..."
python -m data_pipeline.ingestion.upload_to_hdfs --year $YEAR

echo ""
echo "========================================"
echo "  Pipeline terminée avec succès !"
echo "  Données disponibles dans Hive."
echo "========================================"
