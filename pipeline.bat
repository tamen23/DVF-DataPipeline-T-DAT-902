@echo off
REM Homepedia - Pipeline de données complète
REM Usage: pipeline.bat [year]
REM   SET USE_SPARK=1     -> agrégation gold via PySpark (nécessite Java)
REM   SET SKIP_POSTGRES=1 -> saute le chargement PostgreSQL/dbt

SET YEAR=%1
IF "%YEAR%"=="" SET YEAR=2023
SET /A PREV_YEAR=%YEAR%-1

SET GOLD_MODULE=data_pipeline.transformation.gold_real_estate
IF "%USE_SPARK%"=="1" SET GOLD_MODULE=data_pipeline.spark_jobs.aggregate_dvf

echo.
echo ========================================
echo   HOMEPEDIA - Pipeline de données
echo   Année: %YEAR% (YoY depuis %PREV_YEAR%)
echo   Gold engine: %GOLD_MODULE%
echo ========================================
echo.

REM --- Ingestion ---
echo [1/11] Téléchargement des communes...
py -m data_pipeline.ingestion.ingest_communes
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_communes & pause & exit /b 1)

echo.
echo [2/11] Téléchargement ARCEP...
py -m data_pipeline.ingestion.ingest_arcep
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_arcep & pause & exit /b 1)

echo.
echo [3/11] Téléchargement DVF %PREV_YEAR% (pour calcul YoY)...
py -m data_pipeline.ingestion.ingest_dvf --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_dvf %PREV_YEAR% & pause & exit /b 1)

echo.
echo [4/11] Téléchargement DVF %YEAR%...
py -m data_pipeline.ingestion.ingest_dvf --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_dvf %YEAR% & pause & exit /b 1)

REM --- Transformation Bronze -> Silver -> Gold ---
echo.
echo [5/11] Bronze + Silver + Gold DVF %PREV_YEAR%...
py -m data_pipeline.transformation.bronze_dvf --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: bronze_dvf %PREV_YEAR% & pause & exit /b 1)
py -m data_pipeline.cleaning.silver_dvf --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: silver_dvf %PREV_YEAR% & pause & exit /b 1)
py -m %GOLD_MODULE% --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: gold %PREV_YEAR% & pause & exit /b 1)

echo.
echo [6/11] Bronze + Silver + Gold DVF %YEAR%...
py -m data_pipeline.transformation.bronze_dvf --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: bronze_dvf %YEAR% & pause & exit /b 1)
py -m data_pipeline.cleaning.silver_dvf --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: silver_dvf %YEAR% & pause & exit /b 1)
py -m %GOLD_MODULE% --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: gold %YEAR% & pause & exit /b 1)

echo.
echo [7/11] Contrôles qualité gold %YEAR%...
py -m data_pipeline.quality_checks.check_gold --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: check_gold & pause & exit /b 1)

echo.
echo [8/11] Build Territory Gold %YEAR%...
py -m data_pipeline.transformation.build_territory_gold --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: build_territory_gold & pause & exit /b 1)

echo.
echo [9/11] Prédictions IA (RandomForest sur l'historique DVF)...
SET /A TARGET_YEAR=%YEAR%+2
py -m data_pipeline.ml.predict_prices --target-year %TARGET_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo   [warn] prédiction IA sautée)

echo.
echo [10/11] Upload vers HDFS...
py -m data_pipeline.ingestion.upload_to_hdfs --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: upload_to_hdfs & pause & exit /b 1)

echo.
echo [11/11] Chargement PostgreSQL (dbt)...
IF "%SKIP_POSTGRES%"=="1" (
    echo   [skip] SKIP_POSTGRES=1
) ELSE (
    py -m data_pipeline.export.load_postgres --year %YEAR%
    IF %ERRORLEVEL% NEQ 0 (echo ERREUR: load_postgres & pause & exit /b 1)
)

echo.
echo ========================================
echo   Pipeline terminée avec succès !
echo   Données disponibles dans Hive et PostgreSQL.
echo ========================================
echo.
pause
