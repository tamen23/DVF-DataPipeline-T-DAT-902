@echo off
REM Homepedia - Pipeline de données complète
REM Usage: pipeline.bat [year]

SET YEAR=%1
IF "%YEAR%"=="" SET YEAR=2023
SET /A PREV_YEAR=%YEAR%-1

echo.
echo ========================================
echo   HOMEPEDIA - Pipeline de données
echo   Année: %YEAR% (YoY depuis %PREV_YEAR%)
echo ========================================
echo.

REM --- Ingestion ---
echo [1/8] Téléchargement des communes...
py -m data_pipeline.ingestion.ingest_communes
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_communes & pause & exit /b 1)

echo.
echo [2/8] Téléchargement ARCEP...
py -m data_pipeline.ingestion.ingest_arcep
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_arcep & pause & exit /b 1)

echo.
echo [3/8] Téléchargement DVF %PREV_YEAR% (pour calcul YoY)...
py -m data_pipeline.ingestion.ingest_dvf --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_dvf %PREV_YEAR% & pause & exit /b 1)

echo.
echo [4/8] Téléchargement DVF %YEAR%...
py -m data_pipeline.ingestion.ingest_dvf --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: ingest_dvf %YEAR% & pause & exit /b 1)

REM --- Transformation Bronze -> Silver -> Gold ---
echo.
echo [5/8] Bronze + Silver DVF %PREV_YEAR%...
py -m data_pipeline.transformation.bronze_dvf --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: bronze_dvf %PREV_YEAR% & pause & exit /b 1)
py -m data_pipeline.cleaning.silver_dvf --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: silver_dvf %PREV_YEAR% & pause & exit /b 1)
py -m data_pipeline.transformation.gold_real_estate --year %PREV_YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: gold_real_estate %PREV_YEAR% & pause & exit /b 1)

echo.
echo [6/8] Bronze + Silver DVF %YEAR%...
py -m data_pipeline.transformation.bronze_dvf --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: bronze_dvf %YEAR% & pause & exit /b 1)
py -m data_pipeline.cleaning.silver_dvf --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: silver_dvf %YEAR% & pause & exit /b 1)
py -m data_pipeline.transformation.gold_real_estate --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: gold_real_estate %YEAR% & pause & exit /b 1)

echo.
echo [7/8] Build Territory Gold %YEAR%...
py -m data_pipeline.transformation.build_territory_gold --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: build_territory_gold & pause & exit /b 1)

echo.
echo [8/8] Upload vers HDFS...
py -m data_pipeline.ingestion.upload_to_hdfs --year %YEAR%
IF %ERRORLEVEL% NEQ 0 (echo ERREUR: upload_to_hdfs & pause & exit /b 1)

echo.
echo ========================================
echo   Pipeline terminée avec succès !
echo   Données disponibles dans Hive.
echo ========================================
echo.
pause
