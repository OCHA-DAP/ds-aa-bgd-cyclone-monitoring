# libraries
library(shiny)
library(shinyWidgets)
library(sf)
library(tidyverse)
library(leaflet)
library(DT)

# --- Framework settings -------------------------------------------------------
# Bangladesh cyclone AA framework (RC 7 April 2025, USG/ERC 25 April 2025):
# 118 km/h or higher at union level in the six target districts.
TARGET_DISTRICTS <- c("Satkhira", "Khulna", "Barguna", "Patuakhali", "Bhola", "Noakhali")
FRAMEWORK_THRESHOLD <- 118
FRAMEWORK_URL <- paste0(
  "https://www.unocha.org/publications/report/bangladesh/",
  "anticipatory-action-framework-bangladesh-cyclones-2025-version"
)

OCHA_BLUE <- "#009EDB"
ABOVE_COLOR <- "#d03b3b"
BELOW_COLOR <- "#9ec5f4"

# loading union boundaries
unions <- st_read("data/bgd_adm_sel_bbs_20201113_shp.gpkg",
                  layer = "bgd_admbnda_adm4_bbs_20201113", quiet = TRUE)

# Keep only columns used in computations/tables to reduce memory + join overhead
unions_ll <- unions |>
  dplyr::filter(ADM2_EN %in% TARGET_DISTRICTS) |>
  st_transform(crs = 4326) |>
  dplyr::select(ADM1_EN, ADM2_EN, ADM2_PCODE, ADM3_EN, ADM3_PCODE, ADM4_EN, ADM4_PCODE)

# Projected geometry for distance calculations (metres).
# Bangladesh fits well in UTM 46N for this purpose.
unions_m <- st_transform(unions_ll, 32646)
unions_boundary_m <- st_boundary(unions_m)

# Simplified geometry for faster leaflet rendering (~100 m tolerance)
unions_ll_slim <- unions_m |>
  st_simplify(dTolerance = 100, preserveTopology = TRUE) |>
  st_transform(4326)

districts_ll <- unions_m |>
  group_by(ADM2_EN) |>
  summarise(.groups = "drop") |>
  st_simplify(dTolerance = 300, preserveTopology = TRUE) |>
  st_transform(4326)

bbox <- st_bbox(unions_ll)

# Wind speeds are shown rounded DOWN to one decimal, so a union just below
# the threshold (e.g. 117.96) never displays as reaching it (118.0).
floor1 <- function(x) floor(x * 10) / 10
fmt_wind <- function(x) sprintf("%.1f", floor1(x))

wind_at_unions <- function(lon, lat, landfall_wind) {
  point_m <- st_sfc(st_point(c(lon, lat)), crs = 4326) |> st_transform(32646)
  distance_km <- as.numeric(st_distance(unions_boundary_m, point_m)) / 1000
  unions_ll |>
    st_drop_geometry() |>
    mutate(
      distance_km = distance_km,
      wind_reduction_factor = 0.9807 * exp(-0.003 * distance_km),
      wind_speed_union = wind_reduction_factor * landfall_wind
    ) |>
    arrange(desc(wind_speed_union))
}

# --- UI ---------------------------------------------------------------------
label_row <- function(label, input) {
  fluidRow(
    column(6, div(class = "input-label", label)),
    column(6, input)
  )
}

ui <- fluidPage(
  title = "Bangladesh Cyclone Monitoring Tool",
  tags$head(
    tags$meta(name = "description", content = "A tool for monitoring cyclones in Bangladesh."),
    tags$link(rel = "stylesheet",
              href = "https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap"),
    tags$style(HTML(sprintf("
      body { font-family: 'Roboto', sans-serif; color: #222; }
      .app-header {
        display: flex; align-items: center; gap: 18px;
        padding: 10px 16px; margin: 0 -15px 12px;
        border-bottom: 3px solid %1$s; background: #fff;
      }
      .app-header img { height: 44px; }
      .app-header h1 { font-size: 22px; font-weight: 700; color: %1$s; margin: 0; }
      .app-header .subtitle { font-size: 13px; color: #555; margin: 2px 0 0; }
      .well { background: #f4f8fb; border: 1px solid #dde7ef; }
      .input-label { padding-top: 7px; font-weight: 500; }
      .threshold-note { font-size: 12px; color: #555; margin: -6px 0 10px; }
      .threshold-note.changed { color: #b35900; font-weight: 700; }
      .btn-primary, .btn-primary:focus { background: %1$s; border-color: %1$s; }
      .btn-primary:hover { background: #0085ba; border-color: #0085ba; }
      .btn { white-space: normal !important; }
      #input_method .btn { width: 100%%; }
      #input_method .btn.active { background: %1$s; border-color: %1$s; color: #fff; }
      .shiny-download-link { display: block; width: 100%%; }
      .result-banner {
        padding: 10px 14px; border-radius: 5px; margin-bottom: 10px;
        background: #f4f8fb; border-left: 4px solid %1$s; font-size: 15px;
      }
      .result-banner.hit { border-left-color: %2$s; background: #fdf1f1; }
      .contact { margin-top: 16px; font-size: 13px; color: #555; }
      .nav-tabs > li.active > a { color: %1$s; font-weight: 700; }
      a { color: %1$s; }
    ", OCHA_BLUE, ABOVE_COLOR)))
  ),
  div(class = "app-header",
      img(src = "ocha_logo_wide.png", alt = "OCHA"),
      div(h1("Bangladesh Cyclone AA Framework Monitoring Tool"),
          p(class = "subtitle",
            "Estimated wind speed in the unions of the six target districts, from a forecast landfall"))
  ),
  sidebarLayout(
    sidebarPanel(
      width = 3,
      radioGroupButtons(
        inputId = "input_method",
        label = "Landfall location",
        choices = c("Click on map", "Enter manually"),
        selected = "Click on map",
        justified = TRUE
      ),
      label_row("Longitude",
                numericInput("lon", NULL, value = 89.54, step = 0.01, width = "100%")),
      label_row("Latitude",
                numericInput("lat", NULL, value = 22.01, step = 0.01, width = "100%")),
      label_row("Landfall wind (km/h)",
                numericInput("wind_speed", NULL, value = 120, min = 0, step = 1, width = "100%")),
      label_row("Threshold (km/h)",
                numericInput("threshold", NULL, value = FRAMEWORK_THRESHOLD, step = 1, width = "100%")),
      uiOutput("threshold_note"),
      actionButton("compute", "Compute union wind speed", class = "btn-primary", width = "100%"),
      div(style = "margin-top: 10px;",
          downloadButton("download_data", "Download union table (CSV)", width = "100%")),
      div(class = "contact",
          "For questions, contact OCHA Data Science at ",
          tags$a(href = "mailto:ocha-datascience@un.org", "ocha-datascience@un.org"),
          ".")
    ),

    mainPanel(
      width = 9,
      uiOutput("result_banner"),
      tabsetPanel(
        tabPanel("Map", leafletOutput("map", height = 560)),
        tabPanel("District summary", br(), DTOutput("summary_table")),
        tabPanel("Union wind speeds", br(), DTOutput("distance_table")),
        tabPanel("Methodology",
                 div(style = "padding: 15px; font-size: 15px; line-height: 1.6; max-width: 820px;",
                     h3("How the estimate is made"),
                     tags$ol(
                       tags$li("Enter a forecast landfall location and the forecast wind speed at landfall."),
                       tags$li("The distance from the landfall point to each union boundary is measured (UTM 46N)."),
                       tags$li("A wind reduction factor is applied to the landfall wind: ",
                               strong("0.9807 × exp(−0.003 × distance in km)"), "."),
                       tags$li(sprintf("Unions with an estimated wind of %d km/h or higher are flagged.",
                                       FRAMEWORK_THRESHOLD))
                     ),
                     h3("Framework"),
                     p(sprintf(paste(
                       "The framework uses forecasts from five models (BMD, IMD, ECMWF, GFS, JTWC).",
                       "Readiness: at least two forecast %d km/h or higher in the target districts",
                       "3-5 days before landfall. Action: the same, up to 72 hours before landfall.",
                       "Target districts: %s."), FRAMEWORK_THRESHOLD,
                       paste(TARGET_DISTRICTS, collapse = ", "))),
                     p("ECMWF tracks are also checked automatically every hour, with the same",
                       "calculation, and summarised by email."),
                     p(tags$a(href = FRAMEWORK_URL, target = "_blank", "Framework document"))
                 )
        )
      )
    )
  )
)

# --- Server -----------------------------------------------------------------
server <- function(input, output, session) {
  results <- reactiveVal(NULL)

  output$threshold_note <- renderUI({
    changed <- isTRUE(input$threshold != FRAMEWORK_THRESHOLD)
    div(class = paste("threshold-note", if (changed) "changed"),
        if (changed) sprintf("Not the framework threshold (%d km/h)", FRAMEWORK_THRESHOLD)
        else "Framework threshold")
  })

  output$map <- renderLeaflet({
    leaflet() |>
      addTiles(options = tileOptions(opacity = 0.7)) |>
      addPolygons(data = unions_ll_slim, group = "unions", weight = 0.4,
                  color = "#ffffff", fillColor = "#cfd8df", fillOpacity = 0.5,
                  label = ~paste0(ADM4_EN, ", ", ADM2_EN)) |>
      addPolylines(data = st_cast(districts_ll, "MULTILINESTRING"),
                   color = "#52514e", weight = 1.2, opacity = 0.8, group = "districts") |>
      addLabelOnlyMarkers(data = suppressWarnings(st_point_on_surface(districts_ll)),
                          label = ~ADM2_EN,
                          labelOptions = labelOptions(noHide = TRUE, direction = "center",
                                                      textOnly = TRUE,
                                                      style = list("font-weight" = "bold",
                                                                   "font-size" = "12px",
                                                                   "color" = "#222",
                                                                   "text-shadow" = "0 0 3px #fff"))) |>
      addMarkers(lng = 89.54, lat = 22.01, layerId = "landfall", label = "Landfall point") |>
      fitBounds(bbox[["xmin"]], bbox[["ymin"]], bbox[["xmax"]], bbox[["ymax"]])
  })

  observeEvent(input$map_click, {
    if (input$input_method == "Click on map") {
      click <- input$map_click
      updateNumericInput(session, "lat", value = round(click$lat, 3))
      updateNumericInput(session, "lon", value = round(click$lng, 3))
      leafletProxy("map") |>
        addMarkers(lng = click$lng, lat = click$lat, layerId = "landfall", label = "Landfall point")
    }
  })

  observeEvent(input$compute, {
    validate_msg <- NULL
    if (!isTruthy(input$lon) || input$lon < 85 || input$lon > 95)
      validate_msg <- "Longitude must be between 85 and 95."
    else if (!isTruthy(input$lat) || input$lat < 18 || input$lat > 27)
      validate_msg <- "Latitude must be between 18 and 27."
    else if (!isTruthy(input$wind_speed) || input$wind_speed <= 0)
      validate_msg <- "Enter a landfall wind speed above 0 km/h."
    else if (!isTruthy(input$threshold) || input$threshold <= 0)
      validate_msg <- "Enter a threshold above 0 km/h."
    if (!is.null(validate_msg)) {
      showNotification(validate_msg, type = "error")
      return()
    }

    distances <- wind_at_unions(input$lon, input$lat, input$wind_speed) |>
      mutate(above_threshold = wind_speed_union >= input$threshold)

    results(list(
      distances = distances,
      lon = input$lon, lat = input$lat,
      wind = input$wind_speed, threshold = input$threshold
    ))

    map_data <- unions_ll_slim |>
      left_join(distances |> select(ADM4_PCODE, wind_speed_union, above_threshold),
                by = "ADM4_PCODE")

    leafletProxy("map") |>
      addMarkers(lng = input$lon, lat = input$lat, layerId = "landfall", label = "Landfall point") |>
      clearGroup("unions") |>
      addPolygons(
        data = map_data, group = "unions",
        color = "#ffffff", weight = 0.4, fillOpacity = 0.75,
        fillColor = ~ifelse(above_threshold, ABOVE_COLOR, BELOW_COLOR),
        label = ~sprintf("%s, %s: %s km/h", ADM4_EN, ADM2_EN, fmt_wind(wind_speed_union))
      ) |>
      clearControls() |>
      addLegend(position = "bottomright",
                colors = c(ABOVE_COLOR, BELOW_COLOR),
                labels = c(sprintf("%g km/h or higher", input$threshold),
                           sprintf("Below %g km/h", input$threshold)),
                title = "Estimated union wind", opacity = 0.9)
  })

  output$result_banner <- renderUI({
    r <- results()
    if (is.null(r)) {
      return(div(class = "result-banner", HTML(paste0(
        "Pick a landfall point, enter the forecast landfall wind and press ",
        "<strong>Compute union wind speed</strong>."))))
    }
    d <- r$distances
    n_above <- sum(d$above_threshold)
    districts <- sort(unique(d$ADM2_EN[d$above_threshold]))
    detail <- paste0(
      sprintf(" at or above %g km/h", r$threshold),
      if (n_above > 0) sprintf(" (%s)", paste(districts, collapse = ", ")),
      sprintf(". Highest estimate %s km/h. Landfall %.2fN %.2fE at %g km/h.",
              fmt_wind(max(d$wind_speed_union)), r$lat, r$lon, r$wind)
    )
    div(class = paste("result-banner", if (n_above > 0) "hit"),
        HTML(paste0("<strong>", sprintf("%d of %d unions", n_above, nrow(d)),
                    "</strong>", htmltools::htmlEscape(detail))))
  })

  output$summary_table <- renderDT({
    r <- results()
    req(r)
    summary_data <- r$distances |>
      group_by(ADM1_EN, ADM2_EN) |>
      summarize(
        above = sum(above_threshold),
        total = n(),
        share = above / total,
        max_wind = floor1(max(wind_speed_union)),
        .groups = "drop"
      ) |>
      arrange(desc(max_wind))
    datatable(
      summary_data,
      colnames = c("Division", "District", "Unions at or above threshold", "Total unions",
                   "Share", "Highest union wind (km/h)"),
      options = list(dom = "t", paging = FALSE, searching = FALSE,
                     columnDefs = list(list(className = "dt-center", targets = 2:5))),
      rownames = FALSE
    ) |>
      formatPercentage("share", 0) |>
      formatRound("max_wind", 1)
  })

  output$distance_table <- renderDT({
    r <- results()
    req(r)
    datatable(
      r$distances |> select(-above_threshold) |>
        mutate(wind_speed_union = floor1(wind_speed_union)),
      colnames = c("Division", "District", "District PCODE", "Upazila", "Upazila PCODE",
                   "Union", "Union PCODE", "Distance (km)", "Wind reduction factor",
                   "Wind speed (km/h)"),
      options = list(pageLength = 50),
      rownames = FALSE
    ) |>
      formatRound(c("distance_km", "wind_speed_union"), 1) |>
      formatRound("wind_reduction_factor", 3) |>
      # styleInterval is strict ">", so step just below the threshold to flag ">="
      formatStyle("wind_speed_union", target = "row",
                  backgroundColor = styleInterval(r$threshold - 1e-9,
                                                  c(NA, "rgba(208, 59, 59, 0.18)")))
  })

  output$download_data <- downloadHandler(
    filename = function() {
      paste0("bgd_union_wind_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".csv")
    },
    content = function(file) {
      r <- results()
      if (is.null(r)) {
        write.csv(data.frame(note = "Press Compute union wind speed first."), file, row.names = FALSE)
      } else {
        write.csv(r$distances, file, row.names = FALSE)
      }
    }
  )
}

# Run App
shinyApp(ui = ui, server = server)
