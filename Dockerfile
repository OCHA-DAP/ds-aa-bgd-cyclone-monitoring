FROM rocker/r-ver:4.5.0

# Set environment variables
ENV RENV_VERSION=1.1.7
ENV CRAN_REPO=https://packagemanager.posit.co/cran/latest
ENV RENV_CONFIG_CACHE_SYMLINKS=TRUE
ENV RENV_CONFIG_NCPUS=max

# ARG DSCI_AZ_BLOB_DEV_SAS
# ENV DSCI_AZ_BLOB_DEV_SAS=$DSCI_AZ_BLOB_DEV_SAS

# Set the R library path explicitly
ENV RENV_PATHS_LIBRARY=/app/renv/library/R-4.5/x86_64-pc-linux-gnu

# Ensure the directory exists
RUN mkdir -p ${RENV_PATHS_LIBRARY}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libudunits2-dev \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libfontconfig1-dev \  
    libfreetype6-dev \     
    libpng-dev \
    libtiff-dev \
    libjpeg-dev \
    libharfbuzz-dev \     
    libfribidi-dev \       
    pkg-config \      
    && rm -rf /var/lib/apt/lists/*

# Install renv and restore packages
RUN R -e "Sys.setenv(RENV_PATHS_LIBRARY='${RENV_PATHS_LIBRARY}'); \
          .libPaths(c('${RENV_PATHS_LIBRARY}', .libPaths())); \
          print('===== Before installing remotes ====='); print(.libPaths()); \
          options(repos = c(CRAN = '${CRAN_REPO}')); \
          install.packages('remotes'); \
          print('===== After installing remotes ====='); print(.libPaths()); \
          install.packages('renv'); \
          print('===== After installing renv ====='); print(.libPaths()); \
          installed_pkgs <- installed.packages(); \
          print('===== Installed packages in RENV_PATHS_LIBRARY ====='); print(installed_pkgs[, c('Package', 'LibPath')])"
          
# Create & set working directory
WORKDIR /app

# Copy lockfile first (to enable Docker caching)
COPY renv.lock .

# Explicitly restore to the correct library
RUN R -e "Sys.setenv(RENV_PATHS_LIBRARY='${RENV_PATHS_LIBRARY}'); \
           .libPaths(c('${RENV_PATHS_LIBRARY}', .libPaths())); \
           renv::restore(prompt=FALSE, clean=TRUE, rebuild=TRUE); \
           if (!requireNamespace('shiny', quietly=TRUE)) install.packages('shiny', repos='${CRAN_REPO}', lib='${RENV_PATHS_LIBRARY}')"

# Copy the rest of the app
COPY . .

# Expose port for Shiny app
EXPOSE 3838

# Run the Shiny app with the correct library path
CMD R -e "renv::load(); .libPaths(c(Sys.getenv('RENV_PATHS_LIBRARY'), .libPaths())); shiny::runApp('app.R', host = '0.0.0.0', port = 3838)"
