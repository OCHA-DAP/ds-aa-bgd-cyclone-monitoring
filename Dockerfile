FROM rocker/r-ver:4.3.3

# Set environment variables
ENV RENV_VERSION=v1.1.3
ENV RENV_CONFIG_REPOS_OVERRIDE https://cloud.r-project.org
ENV RENV_CONFIG_NCPUS max
# ARG DSCI_AZ_BLOB_DEV_SAS
# ENV DSCI_AZ_BLOB_DEV_SAS=$DSCI_AZ_BLOB_DEV_SAS

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libudunits2-dev \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Install renv from GitHub
RUN R -e "install.packages('remotes', repos = 'https://packagemanager.posit.co/cran/latest'); remotes::install_github('rstudio/renv@${RENV_VERSION}')"

# Create & set working directory
WORKDIR /app

# Copy lockfile first (to enable Docker caching)
COPY renv.lock /app/

# Restore renv environment (only runs if renv.lock changes)
RUN R -e "renv::restore()"

# Copy the rest of the app
COPY . /app/

# Expose port for Shiny app
EXPOSE 3838

# Run the Shiny app
CMD ["R", "-e", "shiny::runApp('./app.R', host='0.0.0.0', port=3838)"]