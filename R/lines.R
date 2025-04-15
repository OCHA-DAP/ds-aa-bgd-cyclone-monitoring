#docker builder prune -a

#docker build -t ds-aa-bgd-cyclone-monitoring .
#docker build --cache-from ds-aa-bgd-cyclone-monitoring -t ds-aa-bgd-cyclone-monitoring .
#docker build --build-arg DSCI_AZ_BLOB_DEV_SAS=$Env:DSCI_AZ_BLOB_DEV_SAS -t ds-aa-bgd-cyclone-monitoring .

#docker run --rm -it ds-aa-bgd-cyclone-monitoring ls /app

#docker run -p 3838:3838 ds-aa-bgd-cyclone-monitoring
#docker run --env DSCI_AZ_BLOB_DEV_SAS -p 3838:3838 ds-aa-bgd-cyclone-monitoring

#renv::init()
#renv::install(c("shiny", "sf", "tidyverse", "leaflet", "DT", "leaflet.extras", "AzureStor", "shinyWidgets"))
#renv::snapshot()

#docker run -it ds-aa-bgd-cyclone-monitoring R
#installed.packages()[,1]
#renv::status()
#.libPaths()
