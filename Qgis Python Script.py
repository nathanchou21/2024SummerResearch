import os 
import re
import pandas as pd
from shapely.geometry import LineString
import geopandas as gpd
import numpy as np
from PyQt5.QtCore import QVariant
import matplotlib.pyplot as plt
from console.console import _console
from pathlib import Path

PROJECT_PATH = Path(_console.console.tabEditorWidget.currentWidget().path).parent
DROUGHT_ECOREGION_DIR = str(PROJECT_PATH / "Droughts Across Ecoregions")
INTERPOLATE_SPI_DIR = str(PROJECT_PATH / "Interpolating SPI Data")
DROUGHT_SPECIES_DIR = str(PROJECT_PATH / "Droughts Experienced By Species")
FINAL_CSV_DIR = str(PROJECT_PATH / "Csv Files")
SPECIES_POP_DIR = str(PROJECT_PATH / "Species Population Trends")
PROJECT = QgsProject.instance()

LECONTES = "lecontes_sparrow"
SAVANNA = "savanna_sparrow"
GRASSHOPPER = "grasshopper_sparrow"
BIRD_TO_AOU_CODE = {LECONTES: 5480, SAVANNA: 5420, GRASSHOPPER: 5460}
NABBS_COUNTRY_CODES = {124: "United States", 840: "Canada"}
NABBS_STATE_CODES = {
2 : "Alabama", 3 : "Alaska", 4 : "Alberta", 6 : "Arizona", 7 : "Arkansas", 11 : "British Columbia", 14 : "California", 17 : "Colorado", 18 : "Connecticut", 21 : "Delaware", 25 : "Florida", 27 : "Georgia", 33 : "Idaho", 34 : "Illinois", 35 : "Indiana", 36 : "Iowa", 38 : "Kansas", 39 : "Kentucky", 42 : "Louisiana", 43 : "Northwest Territories", 44 : "Maine", 45 : "Manitoba", 46 : "Maryland", 47 : "Massachusetts", 49 : "Michigan", 50 : "Minnesota", 51 : "Mississippi", 52 : "Missouri", 53 : "Montana", 54 : "Nebraska", 55 : "Nevada", 56 : "New Brunswick", 57 : "Newfoundland and Labrador", 58 : "New Hampshire", 59 : "New Jersey", 60 : "New Mexico", 61 : "New York", 62 : "Nunavut", 63 : "North Carolina", 64 : "North Dakota", 65 : "Nova Scotia", 66 : "Ohio", 67 : "Oklahoma", 68 : "Ontario", 69 : "Oregon", 72 : "Pennsylvania", 75 : "Prince Edward Island", 76 : "Quebec", 77 : "Rhode Island", 79 : "Saskatchewan", 80 : "South Carolina", 81 : "South Dakota", 82 : "Tennessee", 83 : "Texas", 85 : "Utah", 87 : "Vermont", 88 : "Virginia", 89 : "Washington", 90 : "West Virginia", 91 : "Wisconsin", 92 : "Wyoming", 93 : "Yukon"}


LATITUDE = 42.305

#Helper Functions
def delete_layer(layer_name):
    for layer in PROJECT.mapLayers().values():
        if layer.name() == layer_name:
            PROJECT.removeMapLayer(layer)

def add_replace_layer(path,  type, layer_name,layer_to_delete = ""):
    delete_layer(layer_to_delete)
    delete_layer(layer_name)
    if type == "raster":
        succesful = iface.addRasterLayer(path, layer_name, "gdal")
    elif type == "vector":
        succesful = iface.addVectorLayer(path, layer_name, "ogr")
    else:
        succesful = False
    if not succesful:
        print(layer_name + " layer failed to load!")
        
def add_replace_v_layer(path, layerName, layer_to_delete = ""):
    add_replace_layer(path, 'vector', layerName, layer_to_delete =layer_to_delete)
    
def add_replace_r_layer(path, layerName, layer_to_delete = ""):
    add_replace_layer(path, 'raster', layerName, layer_to_delete=layer_to_delete)



def process_stations():    
    spi_dict = {1:None, 2: None, 3: None}

    #Creates dataframe with SPI data
    for i in range(1,4):
        path_header = INTERPOLATE_SPI_DIR + '/original_data/0' + str(i) + 'mon-spi'
        canada_df = pd.read_csv(path_header + '-cn.csv', header = None, names= ["Station", "Element_Code", "Year"] + [*range(1,13)])
        us_df = pd.read_csv(path_header + '-us.csv', header = None, names= ["Station", "Element_Code", "Year"] + [*range(1,13)])
        combined_df = pd.concat([canada_df, us_df]).reset_index(drop = True)
        combined_df = combined_df[combined_df['Year'] > 2018].drop(['Element_Code'], axis = 1)
        df_melted = pd.melt(combined_df, id_vars=["Station", "Year"], var_name="Month", value_name="Spi")
        df_melted["Year_month"] = pd.to_datetime(df_melted["Year"].astype(str) + "-" + df_melted["Month"].astype(str),format='%Y-%m')
        df_melted = df_melted.sort_values(by = ["Year_month"])
        spi_df = df_melted.pivot(index="Station", columns="Year_month", values="Spi")
        spi_dict[i] = spi_df

        
    #Creates a dataframe with all the stations and their lat/long locations
    can_stations_df = pd.read_csv(INTERPOLATE_SPI_DIR + '/original_data/can-metadata.csv', header = None, names= ["Station", "Latitude", "Longitude", "District", "Division", "Drop"])
    can_stations_df = can_stations_df.drop([ "District", "Division", "Drop"], axis = 1)
    us_stations_df = pd.read_csv(INTERPOLATE_SPI_DIR + '/original_data/us48-div-metadata.csv', header = None, names= ["Station", "Latitude", "Longitude", "District", "Division", "Drop"])
    us_stations_df = us_stations_df.drop([ "District", "Division", "Drop"], axis = 1)
    stations_df = pd.concat([us_stations_df, can_stations_df]).reset_index(drop = True)
    stations_df = stations_df[stations_df['Station'].isin(spi_dict[1].index.to_series().values)]
    
    #Creates a shape file from this dataframe
    station_locs = gpd.points_from_xy(stations_df.Longitude, stations_df.Latitude)
    stations_gdf = gpd.GeoDataFrame(stations_df.Station, geometry=station_locs)
    stations_gdf.to_file(INTERPOLATE_SPI_DIR + '/spi_stations/spi_stations.shp', driver = "Shapefile", crs=4326)

    add_replace_v_layer(INTERPOLATE_SPI_DIR + '/spi_stations/spi_stations.shp', "spi_stations")

    # add SPI data to the shape file of stations

    station_layer = PROJECT.mapLayersByName('spi_stations')[0]
    station_layer.startEditing()

    # Add SPI data into shapefile using 1,2,3 month SPI data for each month
    for spi_type in range(1,4):
        spi_df = spi_dict[spi_type]
        for month in range(1,13):
            for year in range(2019, 2024):
                attribute = str(month) + "-" + str(year-2000)+ "_" + str(spi_type)
                station_layer.addAttribute(QgsField(attribute, QVariant.Double))
                year_month = pd.to_datetime(str(year) + "-" + str(month), format='%Y-%m')
                
                for station in station_layer.getFeatures():
                     qvariant_double = QVariant(float(spi_df.loc[station['Station'], spi_df.columns == year_month]))
                     station[attribute] = qvariant_double
                     station_layer.updateFeature(station)
                
    station_layer.commitChanges()


def process_regions():
    add_replace_v_layer(DROUGHT_ECOREGION_DIR + '/original_data/na_cec_eco_l2/NA_CEC_Eco_Level2.shp', "NA_CEC_Eco_Level2")

    #reproject ecoregions to EPSG:4326 CRS
    processing.run("native:reprojectlayer", 
    {'INPUT': DROUGHT_ECOREGION_DIR + '/original_data/na_cec_eco_l2/NA_CEC_Eco_Level2.shp',
    'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:4326'),
    'CONVERT_CURVED_GEOMETRIES':False,
    'OPERATION':'+proj=pipeline +step +inv +proj=laea +lat_0=45 +lon_0=-100 +x_0=0 +y_0=0 +ellps=sphere +step +proj=unitconvert +xy_in=rad +xy_out=deg',
    'OUTPUT':DROUGHT_ECOREGION_DIR + "/ecoregions/ecoregions.shp"})
    add_replace_v_layer(DROUGHT_ECOREGION_DIR + "/ecoregions/ecoregions.shp", "ecoregions", layer_to_delete = "NA_CEC_Eco_Level2")

    #delete irrelevant ecoregions
    ecoregion_layer = PROJECT.mapLayersByName('ecoregions')[0]
    ecoregion_layer.startEditing()
    for ecoregion in ecoregion_layer.getFeatures():
        if (not re.match("9\.(2|3|4)|5.4", ecoregion['NA_L2CODE'])):
            ecoregion_layer.deleteFeature(ecoregion.id())
    ecoregion_layer.commitChanges()
            
    #Split ecoregions into north and south
    line = LineString([(180, LATITUDE), (-180, LATITUDE)])
    line_gdf = gpd.GeoDataFrame(pd.DataFrame({'a': ['x']}), geometry=[line], crs='EPSG:4326')
    line_gdf.to_file(DROUGHT_ECOREGION_DIR + "/ecoregions/latitude_line/latitude_line.shp", driver="ESRI Shapefile")
    add_replace_v_layer(DROUGHT_ECOREGION_DIR + "/ecoregions/latitude_line/latitude_line.shp", "latitude_line", layer_to_delete= "latitude_line")
    line_layer = PROJECT.mapLayersByName('latitude_line')[0]
    processing.run("native:splitwithlines", {
    'INPUT': ecoregion_layer,
    'LINES': line_layer,
    'OUTPUT': DROUGHT_ECOREGION_DIR + "/ecoregions/ecoregions_split_NS.shp"
    })
    add_replace_v_layer(DROUGHT_ECOREGION_DIR + "/ecoregions/ecoregions_split_NS.shp", "ecoregions_split_NS", layer_to_delete= 'ecoregions')

    #Label each region as north or south
    split_layer = PROJECT.mapLayersByName('ecoregions_split_NS')[0]
    split_layer.startEditing()
    split_layer.addAttribute(QgsField("NS", QVariant.Double))
    split_layer.updateFields()
    for region in split_layer.getFeatures():
        ns = (region.geometry().centroid().asPoint().y() > LATITUDE)
        region.setAttribute("NS", QVariant(True) if ns else QVariant(False))
        split_layer.updateFeature(region)
    split_layer.commitChanges()


def interpolate_spi():
    station_layer = PROJECT.mapLayersByName('spi_stations')[0]
    for spi_type in range(1,4):
        for month in range(1,13):
            for year in range(2019, 2024):
                attribute = str(month) + "-" + str(year-2000)+ "_" + str(spi_type)
                attribute_idx = station_layer.fields().indexOf(attribute)
                processing.run("qgis:idwinterpolation", 
                {'INTERPOLATION_DATA':INTERPOLATE_SPI_DIR + '/spi_stations/spi_stations.shp::~::0::~::'+str(attribute_idx)+'::~::0',
                'DISTANCE_COEFFICIENT':99,
                'EXTENT':'-178.279251880,-49.946809133,5.315354251,75.811875491 [EPSG:4326]',
                'PIXEL_SIZE':0.5,
                'OUTPUT':INTERPOLATE_SPI_DIR + '/spi_stations/interpolated_spi/'+ attribute + ".tif"})
               
            

def average_spi_in_regions():
    current_adress = DROUGHT_ECOREGION_DIR + "/ecoregions/ecoregions_split_NS.shp"
    for spi_type in range(1,4):
        for month in range(1,13):
            for year in range(2019, 2024):
                attribute = str(month) + "-" + str(year-2000)+ "_" + str(spi_type)
                next_adress = DROUGHT_ECOREGION_DIR + "/ecoregions/ecoregions_"+ attribute+'.shp'
                processing.run("native:zonalstatisticsfb", 
                {'INPUT':current_adress,
                'INPUT_RASTER':INTERPOLATE_SPI_DIR + '/spi_stations/interpolated_spi/'+ attribute + ".tif",
                'RASTER_BAND':1,
                'COLUMN_PREFIX':attribute,
                'STATISTICS':[2],
                'OUTPUT':next_adress})
                current_adress = next_adress
    add_replace_v_layer(current_adress, "ecoregions_with_average_spi" ,layer_to_delete= 'ecoregions_split_NS')

        
def create_ecoregions_csv():

    averaged_ecoregions = PROJECT.mapLayersByName('ecoregions_with_average_spi')[0]
    field_names = [field.name() for field in averaged_ecoregions.fields()]
    attributes = []

    for region in averaged_ecoregions.getFeatures():
        attrs = region.attributes()
        attributes.append(attrs)

    attribute_table_df = pd.DataFrame(attributes)
    attribute_table_df.columns = field_names
    attribute_table_df = attribute_table_df.drop(['NA_L1CODE', 'NA_L1NAME', 'NA_L2KEY', 'NA_L1KEY', 'Shape_Leng'], axis = 1)

    # Define a function to calculate the weighted average
    def weighted_average(to_merge_df):
         areas = to_merge_df['Shape_Area']
         just_averages = to_merge_df.drop(['Shape_Area', 'NA_L2CODE', 'NA_L2NAME', 'NS'], axis = 1)
         downscaled = just_averages.mul(areas, axis = 0)
         summed = downscaled.sum()
         upscaled = summed.div(areas.sum())
         return upscaled
    


     # Group by the first two columns and apply the weighted average function
    original_regions = attribute_table_df.groupby(['NA_L2NAME'], as_index = False).apply(weighted_average)
    northern_southern_regions = attribute_table_df.groupby(['NS'], as_index = False).apply(weighted_average)
    
    graph_sets = {}
    graph_sets['Boreal Plain'] = original_regions[original_regions['NA_L2NAME'] == 'BOREAL PLAIN']
    graph_sets['Temperate Prairies'] = original_regions[original_regions['NA_L2NAME'] == 'TEMPERATE PRAIRIES']
    graph_sets['West Central Prairies']= original_regions[original_regions['NA_L2NAME'] == 'WEST-CENTRAL SEMIARID PRAIRIES']
    graph_sets['South Central Prairies'] = original_regions[original_regions['NA_L2NAME'] == 'SOUTH CENTRAL SEMIARID PRAIRIES']
    graph_sets['Northern Prairies'] = northern_southern_regions[northern_southern_regions['NS'] == QVariant(True)]
    graph_sets['Southern Prairies'] = northern_southern_regions[northern_southern_regions['NS'] == QVariant(False)]

    for set in graph_sets: 
         spi_df = graph_sets[set]
         spi_df = spi_df.drop(spi_df.columns[0], axis = 1).melt()
         measurement_specs = spi_df['variable'].str.split('-|_', expand = True)
         measurement_specs.columns = ['Month', "Year", 'SPI Type']
         measurement_specs['SPI Type'] = measurement_specs['SPI Type'].str.split('mea', expand = True)[0]
         measurement_specs['Month'] = measurement_specs['Month'].astype(int)
         measurement_specs['Year'] = measurement_specs['Year'].astype(int).add(2000)
         annual_spi_df = pd.concat([measurement_specs, spi_df['value']], axis = 1)
         annual_spi_df = annual_spi_df.pivot(columns = 'Year', index = ['SPI Type', 'Month'], values = 'value')
         annual_spi_df.to_csv(FINAL_CSV_DIR + "/"+ set + "_annual_spis.csv")

         to_date_time = measurement_specs.drop('SPI Type', axis = 1)
         to_date_time['Day'] = 1
         to_date_time = pd.to_datetime(to_date_time).dt.strftime('%Y-%m').rename('Date')
         monthly_spi_df = pd.concat([to_date_time, measurement_specs['SPI Type'], spi_df['value']], axis = 1)
         monthly_spi_df.to_csv(FINAL_CSV_DIR + "/"+ set + "_monthly_spis.csv")

def regional_spi_process():
    process_stations()
    process_regions()
    interpolate_spi()
    average_spi_in_regions()
    create_ecoregions_csv()


def normalize_abundance(bird, season):
    
    if (season == 'breeding'): 
        fid = 0
    elif (season == 'nonbreeding'): 
        fid = 2
    else:
        raise Exception("season should be breeding or nonbreeding")

    processing.run("native:zonalstatisticsfb", 
             {'INPUT':DROUGHT_SPECIES_DIR + '/range_files/'+ bird + '_range.gpkg',
             'INPUT_RASTER':DROUGHT_SPECIES_DIR + '/abundance_files/'+ bird + "_" + season + "_abundance.tif",
             'RASTER_BAND':1,
             'COLUMN_PREFIX':bird[:5] + "_" + season[:4],
             'STATISTICS':[2],
             'OUTPUT': DROUGHT_SPECIES_DIR + '/range_files/'+bird + "_" + season + '_range_w_mean_abd_.shp'})

    add_replace_v_layer(DROUGHT_SPECIES_DIR + '/range_files/'+bird + "_" + season + '_range_w_mean_abd_.shp', 'temp')

    my_layer = PROJECT.mapLayersByName('temp')[0]
    feature = next(my_layer.getFeatures(QgsFeatureRequest().setFilterFid(fid)))
    idx = my_layer.fields().indexFromName(bird[:5] + "_" + season[:4])
    average = feature.attributes()[idx]
   

    processing.run("native:rastercalc", 
                {'LAYERS':[DROUGHT_SPECIES_DIR + '/abundance_files/'+ bird + "_" + season + "_abundance.tif"],
                'EXPRESSION':'"'+ bird + "_" + season +'_abundance@1" / ' + str(average),
                'EXTENT':None,
                'CELL_SIZE':None,
                'CRS':QgsCoordinateReferenceSystem('EPSG:4326'),
                'OUTPUT':DROUGHT_SPECIES_DIR + '/abundance_files/'+ bird + "_" + season + "_abundance_normalized.tif"})
    


def scale_interpolated_spi(bird, season):
     
    for spi_type in range(1,4):
        for month in range(1,13):
            for year in range(2019, 2024):
                attribute = str(month) + "-" + str(year-2000)+ "_" + str(spi_type)
                processing.run("native:rastercalc", 
                {'LAYERS':[DROUGHT_SPECIES_DIR + '/abundance_files/'+ bird + "_" + season + "_abundance_normalized.tif",INTERPOLATE_SPI_DIR + '/spi_stations/interpolated_spi/'+ attribute + ".tif"],
                'EXPRESSION':'"'+ bird + "_" + season + '_abundance_normalized@1" * "' + attribute + '@1"',
                'EXTENT':None,
                'CELL_SIZE':None,
                'CRS':QgsCoordinateReferenceSystem('EPSG:4326'),
                'OUTPUT':DROUGHT_SPECIES_DIR + '/scaled_interpolations/'+ bird + "_" + season+ "_"+ attribute +"scaled_interp.tif"})

             
#TODO This should hand off to the calculate spi in region method
def calculateAverage(bird, season): 
    current_adress = DROUGHT_SPECIES_DIR + '/range_files/'+ bird + '_range.gpkg'
    for spi_type in range(1,4):
        for month in range(1,13):
            for year in range(2019, 2024):
                attribute = str(month) + "-" + str(year-2000)+ "_" + str(spi_type)
                next_adress = DROUGHT_SPECIES_DIR + '/range_files/'+ bird + "_" + season+ "_"+ attribute  + '_range.gpkg'
                processing.run("native:zonalstatisticsfb", 
                {'INPUT':current_adress,
                'INPUT_RASTER':DROUGHT_SPECIES_DIR + '/scaled_interpolations/'+ bird + "_" + season+ "_"+ attribute  +"scaled_interp.tif",
                'RASTER_BAND':1,
                'COLUMN_PREFIX':attribute,
                'STATISTICS':[2],
                'OUTPUT':next_adress})
                current_adress = next_adress
    add_replace_v_layer(current_adress, bird + "_" + season +"_spi", layer_to_delete= "temp")

def experienced_spi_process(bird, season):
    normalize_abundance(bird, season)
    scale_interpolated_spi(bird, season)
    calculateAverage(bird, season)
    create_experienced_spi_csv(bird, season)

#TODO This has some repeat code with the firs create csv function
def create_experienced_spi_csv(bird, season):

    averaged_ecoregions = PROJECT.mapLayersByName(bird + "_" + season +"_spi")[0]
    field_names = [field.name() for field in averaged_ecoregions.fields()]
    attributes = []

    for region in averaged_ecoregions.getFeatures():
        attrs = region.attributes()
        attributes.append(attrs)

    spi_df = pd.DataFrame(attributes)
    spi_df.columns = field_names
    spi_df = spi_df[spi_df['season'] == season]
    spi_df = spi_df.drop(['fid', 'species_code', 'scientific_name', 'common_name', 'prediction_year', 'type', 'season', 'start_date', 'end_date'], axis = 1)
    
    spi_df = spi_df.melt()
    measurement_specs = spi_df['variable'].str.split('-|_', expand = True)
    measurement_specs.columns = ['Month', "Year", 'SPI Type']
    measurement_specs['SPI Type'] = measurement_specs['SPI Type'].str.split('mea', expand = True)[0]
    measurement_specs['Month'] = measurement_specs['Month'].astype(int)
    measurement_specs['Year'] = measurement_specs['Year'].astype(int).add(2000)
    annual_spi_df = pd.concat([measurement_specs, spi_df['value']], axis = 1)
    annual_spi_df = annual_spi_df.pivot(columns = 'Year', index = ['SPI Type', 'Month'], values = 'value')
    annual_spi_df.to_csv(FINAL_CSV_DIR + "/"+ bird + "_" + season + "_annual_spis.csv")

    to_date_time = measurement_specs.drop('SPI Type', axis = 1)
    to_date_time['Day'] = 1
    to_date_time = pd.to_datetime(to_date_time).dt.strftime('%Y-%m').rename('Date')
    monthly_spi_df = pd.concat([to_date_time, measurement_specs['SPI Type'], spi_df['value']], axis = 1)
    monthly_spi_df.to_csv(FINAL_CSV_DIR + "/"+ bird + "_" + season + "_monthly_spis.csv")

def create_ebird_effort_csv():
    effort_df = pd.DataFrame()
    for country in ['mexico', 'canada', 'us']:
        for df in pd.read_csv(FINAL_CSV_DIR + '/' + country + '_sampling.txt', delimiter = "	", chunksize= 10000):
            df = df[df['ALL SPECIES REPORTED'] == 1]
            df = df[['COUNTRY',  'STATE', 
            'COUNTY', 'OBSERVATION DATE','DURATION MINUTES']].dropna()
            df['OBSERVATION DATE'] = pd.to_datetime(df['OBSERVATION DATE'], format='%Y-%m-%d').dt.to_period('M')
            df = pd.DataFrame(df.groupby(['COUNTRY',  'STATE', 
            'COUNTY', 'OBSERVATION DATE',])['DURATION MINUTES'].sum().reset_index())
            effort_df = pd.concat([effort_df, df], axis = 0)
    effort_df = pd.DataFrame(effort_df.groupby(['COUNTRY',  'STATE', 
    'COUNTY', 'OBSERVATION DATE',])['DURATION MINUTES'].sum().reset_index())
    effort_df.to_csv(FINAL_CSV_DIR + "/ebird_effort.csv")

def create_nabbs_csv(bird):

    nabbs_df = pd.DataFrame()
    for i in range(1,11):
        df = pd.read_csv(FINAL_CSV_DIR + '/nabbs_data/fifty'+str(i)+'.csv')
        df = df[df['AOU'] == BIRD_TO_AOU_CODE[bird]].reset_index(drop = True)
        nabbs_df = pd.concat([nabbs_df, df]).reset_index(drop = True)
 
    nabbs_df['value'] = nabbs_df.iloc[:,8:].sum(axis = 1)
    nabbs_df = nabbs_df.groupby(['StateNum', 'CountryNum', 'Year',])['value'].sum().reset_index()
    nabbs_df['STATE'] = nabbs_df['StateNum'].replace(NABBS_STATE_CODES)
    nabbs_df['COUNTRY'] = nabbs_df['CountryNum'].replace(NABBS_COUNTRY_CODES)
    nabbs_df = nabbs_df.rename({'Year': 'Date'},axis =1)
    nabbs_df = nabbs_df[['STATE', 'COUNTRY', 'Date', 'value']]
    nabbs_df.to_csv(FINAL_CSV_DIR + "/" + bird + "_nabbs.csv")


def plot_regional_spi(axs, region, start_date = '2020-01-01', end_date = '2023-12-31', spi_type = 2, annual = True, ignore_before_month = 6, ignore_after_month = 8, color = "BLACK"):

    axs.set_ylabel('SPI', color=color)

    df = pd.read_csv(FINAL_CSV_DIR + '/' + region + '_monthly_spis.csv')
    df = df[df['SPI Type'] == spi_type]
    df['Date'] = pd.to_datetime(df['Date'],format = '%Y-%m')
    plot_helper(df, axs, start_date, end_date, annual, ignore_before_month, ignore_after_month, color, label = region + " SPI")

def plot_experienced_spi(axs, bird, season = 'breeding', start_date = '2020-01-01', end_date = '2023-12-31', spi_type = 2, annual = True, ignore_before_month = 0, ignore_after_month = 12, color = 'RED'):
    
    axs.set_ylabel('Experiennced SPI', color=color)

    df = pd.read_csv(FINAL_CSV_DIR + '/' + bird+'_'+season + '_monthly_spis.csv')
    df = df[df['SPI Type'] == spi_type]
    df['Date'] = pd.to_datetime(df['Date'],format = '%Y-%m')
    plot_helper(df, axs, start_date, end_date, annual, ignore_before_month, ignore_after_month,color, label = bird + " Drought Experienced")



def plot_ebird_population(axs, bird, location_reqs={}, start_date = '2020-01-01', end_date = '2023-12-31', annual = True, ignore_before_month = 0, ignore_after_month = 12, effort_adjusted= True, color = 'BLUE'):
    
    #TODO this may be poorly placed
    axs.set_ylabel('Ebird Observations', color=color)
    
    ebird_df =pd.read_csv(FINAL_CSV_DIR+'/' + bird + '_ebird.txt', delimiter = "	")

    ebird_df = ebird_df[ebird_df['ALL SPECIES REPORTED'] == 1]
    ebird_df = ebird_df[['OBSERVATION COUNT', 'COUNTRY', 'STATE', 'COUNTY', 'OBSERVATION DATE']]

    ebird_df['OBSERVATION DATE'] = pd.to_datetime(ebird_df['OBSERVATION DATE'], format='%Y-%m-%d')

    ebird_df = ebird_df[ebird_df['OBSERVATION COUNT'] != 'X']


    ebird_df['OBSERVATION COUNT'] = ebird_df['OBSERVATION COUNT'].astype(str).astype(float)


    effort_df = pd.read_csv(FINAL_CSV_DIR+'/ebird_effort.csv')
    effort_df['OBSERVATION DATE'] = pd.to_datetime(effort_df['OBSERVATION DATE'], format='%Y-%m')

    for category in location_reqs:
        ebird_df = ebird_df[ebird_df[category] == location_reqs[category]]
        effort_df = effort_df[effort_df[category] == location_reqs[category]]

    ebird_df = ebird_df[['OBSERVATION DATE', 'OBSERVATION COUNT']]
    effort_df = effort_df[['OBSERVATION DATE', 'DURATION MINUTES']]
    ebird_df = ebird_df.rename(columns ={'OBSERVATION DATE': 'Date', 'OBSERVATION COUNT': 'value'})
    effort_df = effort_df.rename(columns ={'OBSERVATION DATE': 'Date', 'DURATION MINUTES': 'value'})


    
    plot_helper(ebird_df, axs, start_date, end_date, annual, ignore_before_month, ignore_after_month, color, effort = effort_df if effort_adjusted else  None, label = bird + " Population")


def plot_nabbs_population(axs, bird, location_reqs={}, start_date = '2020-01-01', end_date = '2023-12-31', color = 'GREEN'):
    
    axs.set_ylabel('NABBS Population', color=color)

    nabbs_df =pd.read_csv(FINAL_CSV_DIR+'/' + bird + '_nabbs.csv')
    nabbs_df['Date'] = pd.to_datetime(nabbs_df['Date'], format='%Y')

    for category in location_reqs:
        nabbs_df = nabbs_df[nabbs_df[category] == location_reqs[category]]

    plot_helper(nabbs_df, axs, start_date, end_date, True, 0, 12, color, label = bird)


def plot_bird_mic_population(axs, bird, start_date = '2020-01-01', end_date = '2023-12-31', annual = True, color = 'Purple'):
    
    axs.set_ylabel('Rice Bird Mic Observations', color=color)
    bird_mic_df = pd.read_csv(FINAL_CSV_DIR+'/bird_mic.csv')
    bird_df = bird_mic_df[bird_mic_df['bird'] == bird]
    bird_df['Date'] = pd.to_datetime(bird_df['Date'], format='%m/%d/%y')
    plot_helper(bird_df, axs, start_date, end_date, annual, 0, 12, color, label = bird + " bird mic observations")



def plot_helper(df, axs, start_date, end_date, annual, ignore_before_month, ignore_after_month, color, effort = None, label = ""):
    df=df[df['Date'] >= pd.to_datetime(start_date, format='%Y-%m-%d')]
    
    df=df[df['Date'] <= pd.to_datetime(end_date, format='%Y-%m-%d')]
    
    df = df[df['Date'].dt.month.ge(ignore_before_month)]
    df = df[df['Date'].dt.month.le(ignore_after_month)]
    if annual:
        df['Date'] = df['Date'].dt.year
    else:
        df['Date'] = df['Date'].dt.to_period('M').dt.to_timestamp()
    df = pd.DataFrame(df.groupby('Date')['value'].sum())

    #TODO STRUCTURE SO REPEAT CODE IS NOT NECESSARY
    if (effort is not None):
        axs.set_ylabel('Observations per 1000 min', color=color)
        effort=effort[effort['Date'] >= pd.to_datetime(start_date, format='%Y-%m-%d')]
        effort=effort[effort['Date'] <= pd.to_datetime(end_date, format='%Y-%m-%d')]
        
        effort = effort[effort['Date'].dt.month.ge(ignore_before_month)]
        effort = effort[effort['Date'].dt.month.le(ignore_after_month)]
        if annual:
            effort['Date'] = effort['Date'].dt.year
        else:
            effort['Date'] = effort['Date'].dt.to_period('M').dt.to_timestamp()
        effort = pd.DataFrame(effort.groupby('Date')['value'].sum())

        df = df.div(effort).mul(1000)
        
    axs.plot(df.index, df['value'], color = color, label = label)
    axs.tick_params(axis='y', labelcolor=color)
    


#regional_spi_process()
# experienced_spi_process(SAVANNA, "breeding")
# experienced_spi_process(SAVANNA, "nonbreeding")
#experienced_spi_process(LECONTES, "breeding")
# experienced_spi_process(LECONTES, "nonbreeding")
# experienced_spi_process(SAVANNA, "breeding")
# experienced_spi_process(SAVANNA, "nonbreeding")
#experienced_spi_process(GRASSHOPPER, "breeding")
# experienced_spi_process(GRASSHOPPER, "nonbreeding")
# create_ebird_effort_csv()
# create_nabbs_csv



plt.close('all')

# fig, ax = plt.subplots()
# plot_experienced_spi(ax, GRASSHOPPER, spi_type = 3, ignore_before_month=6, ignore_after_month=7)
# ax2 = ax.twinx()
# plot_ebird_population(ax2, GRASSHOPPER, color = 'GREEN', ignore_after_month = 8, location_reqs= {'STATE': 'Texas'} )
# ax3 = ax2.twinx()
# plot_bird_mic_population(ax3, GRASSHOPPER)
# ax.legend(loc = 'upper left')
# ax2.legend(loc = 'upper right')
# ax3.legend(loc = 'upper center')
# ax2.set_title("Grasshopper Annual Sparrow per 1000 Min Observing and Three Month SPI Experienced in Breeding Season")

fig, ax = plt.subplots()
plot_experienced_spi(ax, SAVANNA, spi_type = 3, ignore_before_month=6, ignore_after_month=7)
ax2 = ax.twinx()
plot_ebird_population(ax2, SAVANNA, color = 'GREEN', ignore_after_month=8, location_reqs= {'STATE': 'Texas'})
ax3 = ax2.twinx()
plot_bird_mic_population(ax3, SAVANNA)
ax.legend(loc = 'upper left')
ax2.legend(loc = 'upper right')
ax3.legend(loc = 'upper center')
ax2.set_title("Savanna Annual Sparrow per 1000 Min Observing and Three Month SPI Experienced in Breeding Season")

# fig, ax = plt.subplots()
# plot_experienced_spi(ax, LECONTES, spi_type = 3, ignore_before_month=6, ignore_after_month=8)
# ax2 = ax.twinx()
# plot_ebird_population(ax2, LECONTES, color = 'GREEN', ignore_before_month=8, location_reqs= {'STATE': 'Texas'})
# ax3 = ax2.twinx()
# plot_bird_mic_population(ax3, LECONTES)
# ax.legend(loc = 'upper left')
# ax2.legend(loc = 'upper right')
# ax3.legend(loc = 'upper center')
# ax2.set_title("Leconte's Annual Sparrow per 1000 Min Observing and Three Month SPI Experienced in Breeding Season")




fig, ax = plt.subplots()
plot_experienced_spi(ax, SAVANNA, spi_type = 3, annual = False)
ax2 = ax.twinx()
plot_ebird_population(ax2, SAVANNA, annual = False, location_reqs= {'STATE': 'Texas'})
ax.legend(loc = 'upper left')
ax2.legend(loc = 'upper right')
ax2.set_title("Savanna Sparrow Monthly Observations per 1000 min and Three Month SPI Experienced Breeding Range")

# fig, ax = plt.subplots()
# plot_experienced_spi(ax, LECONTES, spi_type = 3, ignore_before_month=6, ignore_after_month=8)
# ax2 = ax.twinx()
# plot_ebird_population(ax2, LECONTES, effort_adjusted= False)
# ax.legend(loc = 'upper left')
# ax2.legend()
# ax2.set_title("Leconte's Sparrow Annual Observations and Three Month SPI Experienced in Breeding Season")

# fig, ax = plt.subplots()
# plot_nabbs_population(ax, GRASSHOPPER, start_date= '2000-01-01')
# plot_nabbs_population(ax, LECONTES, color = 'RED', start_date= '2000-01-01')
# plot_nabbs_population(ax, SAVANNA, color = 'BLACK', start_date= '2000-01-01')
# ax.legend()
# ax.set_title("NABBS Population records")

# fig5, ax = plt.subplots()
# plot_regional_spi(ax, "Northern Prairies", color = 'RED')
# plot_regional_spi(ax, "West Central Prairies", color = 'BLUE')
# plot_regional_spi(ax, "Temperate Prairies")
# ax.legend()
# ax.set_title("Two month SPIs from June to August")

# fig6, ax = plt.subplots()
# plot_experienced_spi(ax, LECONTES, spi_type = 3, annual= False)
# plot_experienced_spi(ax, SAVANNA, spi_type = 3, annual= False, color = "green")
# plot_experienced_spi(ax, GRASSHOPPER, spi_type = 3, annual= False, color = "black")
# ax.legend()
# ax.set_title("Monthly Experienced Spis")

#5126433163


plt.show()

