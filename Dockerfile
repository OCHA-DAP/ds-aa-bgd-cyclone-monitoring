FROM rocker/r-ver:4.3.3

# Set environment variables
ENV RENV_VERSION=v1.1.3
# ARG DSCI_AZ_BLOB_DEV_SAS
# ENV DSCI_AZ_BLOB_DEV_SAS=$DSCI_AZ_BLOB_DEV_SAS

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libudunits2-dev \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Install R packages
RUN R -e "install.packages(c('remotes', 'sf', 'AzureStor', 'httr', 'shiny', 'DT', 'tidyverse', 'leaflet', 'leaflet.extras'), repos = 'https://packagemanager.posit.co/cran/latest')"

# Install renv from GitHub
RUN R -e "remotes::install_github('rstudio/renv@${RENV_VERSION}')"

# Copy application files
COPY . /app
COPY renv.lock /app/

# Set working directory
WORKDIR /app

# Restore renv environment
RUN R -e "options(renv.config.repos.override = 'https://packagemanager.posit.co/cran/latest',renv.verbose = TRUE); renv::restore()"

# Expose port for Shiny app
EXPOSE 3838

# Run the Shiny app
CMD ["R", "-e", "shiny::runApp('./app.R', host='0.0.0.0', port=3838)"]