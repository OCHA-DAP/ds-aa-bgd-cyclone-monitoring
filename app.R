# libraries
library(shiny)
library(shinyWidgets)
library(sf)
library(tidyverse)
library(leaflet)
library(DT)
library(leaflet.extras2)
library(AzureStor)
library(rmapshaper)

# loading union boundaries
temp_file <- "data/bgd_adm_sel_bbs_20201113_shp.gpkg"

# Read the GeoPackage using sf
unions <- st_read(temp_file, layer = "bgd_admbnda_adm4_bbs_20201113", quiet = TRUE)

unions_framework <- unions |>
  dplyr::filter(ADM2_EN %in% c("Barguna","Bhola","Patuakhali","Noakhali","Satkhira","Khulna")) |>
  st_transform(crs = 4326)

# --- Performance precomputation (NO UI changes) ---
# Keep only columns used in computations/tables to reduce memory + join overhead
unions_ll <- unions_framework |>
  dplyr::select(
    ADM1_EN, ADM2_EN, ADM2_PCODE,
    ADM3_EN, ADM3_PCODE,
    ADM4_EN, ADM4_PCODE,
    geom
  )

# Simplify geometry for faster leaflet rendering (tune keep as needed)
unions_ll_slim <- rmapshaper::ms_simplify(unions_ll, keep = 0.05, keep_shapes = TRUE)

# Projected geometry for fast distance calculations (meters)
# Bangladesh fits well in UTM 46N for this purpose
unions_m <- st_transform(unions_ll, 32646)
unions_boundary_m <- st_boundary(unions_m)

# Define UI (UNCHANGED)
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
  fluidRow(style="background-color: #1BB580; margin-bottom: 3px;",
           column(8, h3("Bangladesh Cyclone AA Framework Monitoring Tool", style = "text-align: left;color:white;font-weight:bold;")),
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
          align-items: center;
          flex: 1;
          margin: 4px;
        }
        .btn {
          white-space: normal !important;
          word-break: break-word;
          text-align: center;
        }
        #input_method .btn {
          white-space: normal;
          width: 100%;
          text-align: center;
        }
        #input_method .dummy-icon {
          visibility: hidden;
        }
        .shiny-download-link {
          display: block;
          width: 100%;
          text-align: center;
        }
      ")),
      radioGroupButtons(
        inputId = "input_method",
        label = "Select Input Method:",
        choices = c("Select Location on Map", "Enter Location Manually"),
        selected = "Select Location on Map",
        status = "success",
        justified = TRUE,
        checkIcon = list(
          yes = icon("ok", lib = "glyphicon"),
          no  = icon("remove", lib = "glyphicon")
        )
      ),
      
      fluidRow(
        column(6, div(style = "display: flex; align-items: center;",
                      tags$label("Longitude:", class = "input-label"))),
        column(6, numericInput("lon", NULL, value = 89.54, step = 0.01, width = "100%"))
      ),
      
      fluidRow(
        column(6, div(style = "display: flex; align-items: center;",
                      tags$label("Latitude:", class = "input-label"))),
        column(6, numericInput("lat", NULL, value = 22.01, step = 0.01, width = "100%"))
      ),
      
      fluidRow(
        column(6, div(style = "display: flex; align-items: center;",
                      tags$label("Forecasted Landfall Wind Speed (km/h):", class = "input-label"))),
        column(6, numericInput("wind_speed", NULL, value = 0, step = 1, width = "100%"))
      ),
      
      fluidRow(
        column(6, div(style = "display: flex; align-items: center;",
                      tags$label("Trigger Threshold (km/h):", class = "input-label"))),
        column(6, div(class = "threshold-input",
                      numericInput("threshold", NULL, value = 118, step = 1, width = "100%")))
      ),
      fluidRow(
        column(12, actionButton("compute", "Compute Union Wind Speed", width = "100%")),
        column(12, style = "margin-top: 10px;",
               downloadButton("download_data", "Download Union Wind Speed Table", width = "100%"))
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
  distance_calc <- reactive({
    req(input$lon, input$lat)
    
    user_point_ll <- st_sfc(st_point(c(input$lon, input$lat)), crs = 4326)
    user_point_m  <- st_transform(user_point_ll, 32646)
    
    as.numeric(st_distance(unions_boundary_m, user_point_m)) / 1000
  }) |> bindCache(input$lon, input$lat)
  
  
  # Render Leaflet map (render once; faster geometry)
  output$map <- renderLeaflet({
    leaflet(options = leafletOptions(minZoom = 8)) |>
      addTiles() |>
      addPolygons(
        data = unions_ll_slim,
        group = "unions",
        weight = 1,
        color = "transparent",
        fillOpacity = 0.0,
        fillColor = "transparent"
      )
  })
  
  observeEvent(input$compute, {
    req(input$lon, input$lat, input$threshold)
    
    # Create user point (lon/lat) then transform for distance
    user_point_ll <- st_sfc(st_point(c(input$lon, input$lat)), crs = 4326)
    user_point_m  <- st_transform(user_point_ll, 32646)
    
    # Compute distance to each polygon boundary (fast) in km
    #distance_km <- as.numeric(st_distance(unions_boundary_m, user_point_m)) / 1000
    distance_km <- distance_calc()
    
    # Compute wind stats (table)
    distances <- unions_ll |>
      st_drop_geometry() |>
      mutate(
        distance_km = distance_km,
        wind_reduction_factor = 0.9807 * exp(-0.003 * distance_km),
        wind_speed_union = wind_reduction_factor * input$wind_speed
      ) |>
      select(ADM1_EN,ADM2_EN,ADM2_PCODE,ADM3_EN,ADM3_PCODE,ADM4_EN,ADM4_PCODE,
             distance_km, wind_reduction_factor, wind_speed_union) |>
      arrange(desc(wind_speed_union))
    
    # Summary statistics (unchanged)
    summary_data <- distances |>
      mutate(above_threshold = wind_speed_union > input$threshold) |>
      group_by(ADM1_EN) |>
      summarize(
        Above_Threshold = sum(above_threshold),
        Total_Unions = n(),
        Percent_Triggered = paste0(round(100 * sum(above_threshold) / n(), 1), "%"),
        .groups = "drop"
      )
    
    output$summary_table <- renderDT({
      datatable(
        summary_data,
        colnames = c("Division", "Above Threshold", "Total Unions", "Percent Triggered"),
        options = list(dom = 't', paging = FALSE, searching = FALSE, autoWidth = TRUE,
                       columnDefs = list(list(className = "dt-center", targets = "_all"))),
        rownames = FALSE,
        width = "80%"
      ) |>
        formatStyle(columns = names(summary_data), textAlign = "center")
    })
    
    output$distance_table <- renderDT({
      datatable(
        distances,
        colnames = c("Division","District","PCODE","Upazila","PCODE","Union","PCODE",
                     "Distance (km)", "Wind Reduction Factor", "Wind Speed (km/h)"),
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
    
    # Join wind_speed_union back to polygons for styling (cheap + clean)
    map_data <- unions_ll_slim |>
      left_join(distances |> select(ADM4_PCODE, wind_speed_union), by = "ADM4_PCODE") |>
      mutate(triggered = !is.na(wind_speed_union) & wind_speed_union > input$threshold)
    
    # Update map efficiently (no clearShapes(), no double polygons)
    leafletProxy("map") |>
      clearMarkers() |>
      addMarkers(lng = input$lon, lat = input$lat, popup = "Landfall Point") |>
      clearGroup("unions") |>
      addPolygons(
        data = map_data,
        group = "unions",
        color = "transparent",
        weight = 1,
        fillOpacity = 0.5,
        fillColor = ~ifelse(triggered, "tomato", "#3EB489")
      )
  })
  
  observeEvent(input$map_click, {
    if (input$input_method == "Select Location on Map") {
      click <- input$map_click
      updateNumericInput(session, "lat", value = click$lat)
      updateNumericInput(session, "lon", value = click$lng)
      
      leafletProxy("map") |>
        clearMarkers() |>
        addMarkers(lng = click$lng, lat = click$lat, popup = "Selected Point")
    }
  })
}

# Run App
shinyApp(ui = ui, server = server)