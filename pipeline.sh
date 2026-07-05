#!/bin/bash
# Homepedia - Pipeline de données complète
# Usage: ./pipeline.sh [year]
#   USE_SPARK=1     -> agrégation gold via PySpark (nécessite Java)
#   SKIP_POSTGRES=1 -> saute le chargement PostgreSQL/dbt

YEAR=${1:-2023}
PREV_YEAR=$((YEAR - 1))

GOLD_MODULE=data_pipeline.transformation.gold_real_estate
if [ "${USE_SPARK:-0}" = "1" ]; then
  GOLD_MODULE=data_pipeline.spark_jobs.aggregate_dvf
fi

echo ""
echo "========================================"
echo "  HOMEPEDIA - Pipeline de données"
echo "  Année: $YEAR (YoY depuis $PREV_YEAR)"
echo "  Gold engine: $GOLD_MODULE"
echo "========================================"
echo ""

set -e  # Stop on error

echo "[1/10] Téléchargement des communes..."
python -m data_pipeline.ingestion.ingest_communes

echo ""
echo "[2/10] Téléchargement ARCEP..."
python -m data_pipeline.ingestion.ingest_arcep

echo ""
echo "[3/10] Téléchargement DVF $PREV_YEAR (pour calcul YoY)..."
python -m data_pipeline.ingestion.ingest_dvf --year $PREV_YEAR

echo ""
echo "[4/10] Téléchargement DVF $YEAR..."
python -m data_pipeline.ingestion.ingest_dvf --year $YEAR

echo ""
echo "[5/10] Bronze + Silver + Gold DVF $PREV_YEAR..."
python -m data_pipeline.transformation.bronze_dvf --year $PREV_YEAR
python -m data_pipeline.cleaning.silver_dvf --year $PREV_YEAR
python -m $GOLD_MODULE --year $PREV_YEAR

echo ""
echo "[6/10] Bronze + Silver + Gold DVF $YEAR..."
python -m data_pipeline.transformation.bronze_dvf --year $YEAR
python -m data_pipeline.cleaning.silver_dvf --year $YEAR
python -m $GOLD_MODULE --year $YEAR

echo ""
echo "[7/10] Contrôles qualité gold $YEAR..."
python -m data_pipeline.quality_checks.check_gold --year $YEAR

echo ""
echo "[8/10] Build Territory Gold $YEAR..."
python -m data_pipeline.transformation.build_territory_gold --year $YEAR

echo ""
echo "[9/10] Upload vers HDFS..."
python -m data_pipeline.ingestion.upload_to_hdfs --year $YEAR

echo ""
echo "[10/10] Chargement PostgreSQL (dbt)..."
if [ "${SKIP_POSTGRES:-0}" = "1" ]; then
  echo "  [skip] SKIP_POSTGRES=1"
else
  python -m data_pipeline.export.load_postgres --year $YEAR
fi

echo ""
echo "========================================"
echo "  Pipeline terminée avec succès !"
echo "  Données disponibles dans Hive et PostgreSQL."
echo "========================================"
