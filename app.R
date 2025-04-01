# libraries
library(shiny)
library(shinyWidgets)
library(sf)
library(tidyverse)
library(leaflet)
library(DT)
library(leaflet.extras)
library(AzureStor)

# loading union boundaries

#sas_token <- Sys.getenv("DSCI_AZ_BLOB_DEV_SAS")
#storage_account <- "imb0chd0dev"
#container_name <- "projects"
#gpkg_blob <- "ds-aa-bgd-cyclone-monitoring/raw/cod_ab/bgd_adm_sel_bbs_20201113_shp.gpkg" 

# Create a blob container object
#blob_container <- blob_container(
#  sprintf("https://%s.blob.core.windows.net/%s", storage_account, container_name),
#  sas = sas_token
#)

# Download the GeoPackage to a temporary file
#temp_file <- tempfile(fileext = ".gpkg")
#storage_download(blob_container, src = gpkg_blob, dest = temp_file)
temp_file <- "data/bgd_adm_sel_bbs_20201113_shp.gpkg"

# Read the GeoPackage using sf
unions <- st_read(temp_file, layer = "bgd_admbnda_adm4_bbs_20201113") 
unions_framework <- unions |>
  dplyr::filter(ADM2_EN %in% c("Barguna","Bhola","Patuakhali","Noakhali","Satkhira","Khulna"))
unions_framework <- st_transform(unions_framework, crs = 4326)

# Loading Admin 1
#adm1 <- st_read(shapefile_path, layer = "bgd_admbnda_adm1_bbs_20201113")
#adm1 <- st_transform(adm1, crs = 4326)

# Define UI
ui <- fluidPage(
  title = "Cyclone Monitoring Tool",
  tags$head(
    tags$link(rel = "icon", href = "path/to/favicon.ico"),
    tags$meta(name = "description", content = "A tool for monitoring cyclones in Bangladesh."), 
    tags$meta(name = "keywords", content = "cyclone, monitoring, Bangladesh"),
    tags$link(rel = "stylesheet", href = "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap"),
    tags$style(HTML("
      body {
        font-family: 'Roboto', sans-serif;
      }
      h2 {
        font-family: 'Roboto', sans-serif;
        font-weight: bold;
      }
      .shiny-input-container {
        font-family: 'Roboto', sans-serif;
      }
    "))
  ),
  fluidRow(style="background-color: #1BB580; margin-bottom: 10px;",
    column(8, h2("Bangladesh Cyclone Monitoring Tool", style = "text-align: left;color:white;font-weight:bold;")),
    column(4, div(style = "text-align: right", img(src = "centre_banner_greenbg.png", height = "50px", style = "margin-top:10px;")))
  ),
  sidebarLayout(
    sidebarPanel(
      width = 3,  
      tags$style(HTML("
        .shiny-input-container {
          background-color: #D8F2E9 !important; 
          border-radius: 5px;
          padding: 5px;
        }
        .threshold-input .shiny-input-container {
          background-color: #FFE5B4 !important; 
          border: 2px solid #FFA500 !important;
        }
        .input-label {
          text-align: right;
          flex: 1;
          margin-top: 10px;
        }
      ")),
      radioGroupButtons(
        inputId = "input_method",
        label = "Select Input Method:",
        choices = c("Select on Map", "Enter Coordinates"),
        selected = "Select on Map",
        status = "success",
        justified = TRUE,
        checkIcon = list(yes = icon("ok", lib = "glyphicon"))
      ),
      
      fluidRow(
        column(5, div(style = "display: flex; align-items: center;", 
                      tags$label("Longitude:", class = "input-label"))),
        column(7, numericInput("lon", NULL, value = 89.54, step = 0.01, width = "100%"))
      ),
        
      fluidRow(
        column(5, div(style = "display: flex; align-items: center;", 
                      tags$label("Latitude:", class = "input-label"))),
        column(7, numericInput("lat", NULL, value = 22.01, step = 0.01, width = "100%"))
      ),
      
      fluidRow(
        column(5, div(style = "display: flex; align-items: center;", 
                      tags$label("Wind Speed (km/h):", class = "input-label"))),
        column(7, numericInput("wind_speed", NULL, value = 0, step = 1, width = "100%"))
      ),
      
      fluidRow(
        column(5, div(style = "display: flex; align-items: center;", 
                      tags$label("Threshold (km/h):", class = "input-label"))),
        column(7, div(class = "threshold-input",
                      numericInput("threshold", NULL, value = 118, step = 1, width = "100%")))
      ),
      fluidRow(
        column(12, actionButton("compute", "Compute Wind Speed", width = "100%")),
        column(12, style = "margin-top: 10px;", 
               downloadButton("download_data", "Download Wind Speed Table", width = "100%"))
      ),
      div(style = "margin-top: 9px; font-size: 14px; color: black; text-align: left; font-style: italic; padding-top: 25px; background-color: #F8F9F9; border-radius: 5px;",
          "This tool is in development. For questions, contact Pauline Ndirangu at ",
          tags$a(href="mailto:pauline.ndirangu@un.org", "pauline.ndirangu@un.org.")
      )
    ),
    
    mainPanel(
      width = 9,
      tabsetPanel(
        tabPanel("Map", leafletOutput("map", height = 590)),
        tabPanel("Division Summary Table", DTOutput("summary_table")),
        tabPanel("Wind Speed Table", DTOutput("distance_table")),
        tabPanel("Methodology", 
                 div(style = "padding: 15px; font-size: 16px; line-height: 1.6;",
                     h3("Methodology Overview", style = "font-weight: bold;"),
                     p("This tool estimates wind speeds at different locations using a wind reduction factor based on distance from the landfall point."),
                     h4("Key Steps:"),
                     tags$ul(
                       tags$li("User selects a cyclone landfall location (Longitude, Latitude)."),
                       tags$li("Wind speed is adjusted based on distance to administrative boundaries."),
                       tags$li("A wind reduction factor is applied: ", strong("0.9807 * exp(-0.003 * distance)")),
                       tags$li("Unions with wind speed above the defined threshold are highlighted."),
                       tags$li("Results are displayed on the map and in summary tables.")
                     )
                 )
        )
      )
    )
  )
)

# Define Server
server <- function(input, output, session) {
  
  observeEvent(input$compute, {
    req(input$lon, input$lat, input$threshold)
    
    # Create user point
    user_point <- st_sfc(st_point(c(input$lon, input$lat)), crs = 4326)
    
    # Compute distance to each polygon edge
    distances <- unions_framework %>%
      mutate(distance_km = as.numeric(st_distance(st_geometry(.), user_point) / 1000),
             wind_reduction_factor = 0.9807 * exp(-0.003 * distance_km),
             wind_speed_union = wind_reduction_factor * input$wind_speed) |>
      st_drop_geometry() |>
      select(ADM1_EN,ADM2_EN,ADM2_PCODE,ADM3_EN,ADM3_PCODE,ADM4_EN,ADM4_PCODE, distance_km, wind_reduction_factor, wind_speed_union) |>
      arrange(desc(wind_speed_union))  # Sort by wind speed (Descending)
    # Summary statistics
    summary_data <- distances |>
      mutate(above_threshold = wind_speed_union > input$threshold) |>
      group_by(ADM1_EN) |>
      summarize(
        Above_Threshold = sum(above_threshold),
        Total_Unions = n(),
        Percent_Triggered = paste0(round(100 * sum(above_threshold) / n(), 1), "%")
      )
    
    output$summary_table <- renderDT({
      datatable(
        summary_data,
        colnames = c("Division", "Above Threshold", "Total Unions", "Percent Triggered"),
        options = list(dom = 't', paging = FALSE, searching = FALSE, autoWidth = TRUE, 
                       columnDefs = list(
                         list(className = "dt-center", targets = "_all")  # Center-align all columns
                       )),
        rownames = FALSE,
        width = "80%"
      ) |>
        formatStyle(
          columns = names(summary_data),
          textAlign = "center"
        )
    })
    # Create DataTable with row highlighting if wind speed > threshold
    output$distance_table <- renderDT({
      datatable(
        distances, 
        colnames = c("Division","District","PCODE","Upazila","PCODE","Union","PCODE", "Distance (km)", "Wind Reduction Factor", "Wind Speed (km/h)"),
        options = list(pageLength = 50, autoWidth = TRUE),
        rownames = FALSE
      ) |>
        formatRound(columns = c("distance_km", "wind_reduction_factor", "wind_speed_union"), digits = 2) |>
        formatStyle(
          columns = "wind_speed_union",
          target = "row",
          backgroundColor = styleInterval(input$threshold, c(NA, "rgba(255, 99, 71, 0.5)"))
        )
    })
    output$download_data <- downloadHandler(
      filename = function() {
        paste0("distance_table_", Sys.Date(), "_", format(Sys.time(), "%H%M%S"), ".csv")
      },
      content = function(file) {
        write.csv(distances, file, row.names = FALSE)
      }
    )
    
    # Update map
    leafletProxy("map") |>
      clearMarkers() |>
      addMarkers(lng = input$lon, lat = input$lat, popup = "Landfall Point") |>
      clearShapes() |>
      addPolygons(data = unions_framework, weight = 1, fillColor = "transparent") |>
      addPolygons(
        data = unions_framework,
        color = "transparent", 
        weight = 1, 
        fillOpacity = 0.5,
        fillColor = ~ifelse(unions_framework$ADM4_PCODE %in% distances$ADM4_PCODE & 
                              distances$wind_speed_union[match(unions_framework$ADM4_PCODE, distances$ADM4_PCODE)] > input$threshold, 
                            "tomato", "#3EB489")  
      )
  })
  
  observeEvent(input$map_click, {
    if(input$input_method == "Select on Map") {
      click <- input$map_click
      updateNumericInput(session, "lat", value = click$lat)
      updateNumericInput(session, "lon", value = click$lng)
      # Add marker to map
      leafletProxy("map") %>%
        clearMarkers() %>%
        addMarkers(lng = click$lng, lat = click$lat, popup = "Selected Point")
    }
  })
  
  # Render Leaflet map
  output$map <- renderLeaflet({
    leaflet(options = leafletOptions(minZoom = 8)) |>
      addTiles() |>
      addPolygons(data = unions_framework, weight = 1, fillColor = "transparent")
  })
}

# Run App
shinyApp(ui = ui, server = server)