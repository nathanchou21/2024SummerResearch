import re
import pandas as pd
from shapely.geometry import LineString
import geopandas as gpd
from PyQt5.QtCore import QVariant
import matplotlib.pyplot as plt

PROJECT = QgsProject.instance()
# TODO make this look at where the code is running once I stop running from the python console
DIR_PATH = "/Users/nathanchou/Desktop/2024SummerResearch"
ORIGINAL_DATA_PATH = DIR_PATH + "/originalData"
MONTHS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
LATITUDE = 42.305


# Helper Functions
def delete_layer(layerName):
    for layer in PROJECT.mapLayers().values():
        if layer.name() == layerName:
            PROJECT.removeMapLayer(layer)


# TODO. Should return, and should have optional replace parameter
def add_or_replace_layer(path, layer_name, layer_type, to_delete=""):
    delete_layer(to_delete)
    delete_layer(layer_name)
    if layer_type == "raster":
        successful = iface.addRasterLayer(path, layer_name, "gdal")
    elif layer_type == "vector":
        successful = iface.addVectorLayer(path, layer_name, "ogr")
    else:
        successful = False
    if not successful:
        print(layer_name + " layer failed to load!")


def add_or_replace_v_layer(path, layer_name, to_delete=""):
    add_or_replace_layer(path, layer_name, 'vector', to_delete=to_delete)


def add_or_replace_r_layer(path, layer_name, to_delete=""):
    add_or_replace_layer(path, layer_name, 'vector', to_delete=to_delete)


def clean_data():
    # Creates dataframe with SPI data
    for i in range(1, 4):
        canada_df = pd.read_csv(ORIGINAL_DATA_PATH + '/0' + str(i) + 'mon-spi-cn.csv', header=None,
                                names=["Station", "ElementCode", "Year"] + MONTHS)
        us_df = pd.read_csv(ORIGINAL_DATA_PATH + '/0' + str(i) + 'mon-spi-us.csv', header=None,
                            names=["Station", "ElementCode", "Year"] + MONTHS)
        combined_df = pd.concat([canada_df, us_df]).reset_index().drop('index', axis=1)
        combined_df = combined_df[combined_df['Year'] > 2018].drop(['ElementCode'], axis=1)
        df_melted = pd.melt(combined_df, id_vars=["Station", "Year"], var_name="Month", value_name="Spi")
        df_melted["Year_month"] = pd.to_datetime(df_melted["Year"].astype(str) + "-" + df_melted["Month"],
                                                 format='%Y-%m')
        df_melted = df_melted.sort_values(by=["Year_month"])
        spi_df = df_melted.pivot(index="Station", columns="Year_month", values="Spi")
        spi_df.to_pickle(DIR_PATH + "/spi_df-rollingMonths" + str(i))

    # Creates a dataframe with all the stations and there lat/long locations
    can_stations_df = pd.read_csv(ORIGINAL_DATA_PATH + '/can-metadata.csv', header=None,
                                  names=["Station", "Latitude", "Longitude", "District", "Division", "Drop"])
    can_stations_df = can_stations_df.drop(["District", "Division", "Drop"], axis=1)
    us_stations_df = pd.read_csv(ORIGINAL_DATA_PATH + '/us48-div-metadata.csv', header=None,
                                 names=["Station", "Latitude", "Longitude", "District", "Division", "Drop"])
    us_stations_df = us_stations_df.drop(["District", "Division", "Drop"], axis=1)
    stations_df = pd.concat([us_stations_df, can_stations_df]).reset_index().drop('index', axis=1)
    one_month_df = pd.read_pickle(DIR_PATH + "/spi_df-rollingMonths1")
    stations_df = stations_df[stations_df['Station'].isin(one_month_df.index.to_series().values)]

    # Creates a shape file from this dataframe
    station_locs = gpd.points_from_xy(stations_df.Longitude, stations_df.Latitude)
    stations_gdf = gpd.GeoDataFrame(stations_df.Station, geometry=station_locs)
    stations_gdf.to_file(DIR_PATH + '/stationFiles/stations_gdf.shp', driver="Shapefile", crs=4326)

    # display stations and ecoregions
    add_or_replace_v_layer(DIR_PATH + '/stationFiles/stations_gdf.shp', "stations_gdf")
    add_or_replace_v_layer(ORIGINAL_DATA_PATH + '/na_cec_eco_l2/NA_CEC_Eco_Level2.shp', "ecoregions")

    # reproject ecoregions
    processing.run("native:reprojectlayer",
                   {'INPUT': ORIGINAL_DATA_PATH + '/na_cec_eco_l2/NA_CEC_Eco_Level2.shp',
                    'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326'),
                    'CONVERT_CURVED_GEOMETRIES': False,
                    'OPERATION': '+proj=pipeline +step +inv +proj=laea +lat_0=45 +lon_0=-100 +x_0=0 +y_0=0 +ellps=sphere +step +proj=unitconvert +xy_in=rad +xy_out=deg',
                    'OUTPUT': DIR_PATH + "/ecoregionFiles/reprojected.shp"})
    add_or_replace_v_layer(DIR_PATH + "/ecoregionFiles/reprojected.shp", "ecoregionsReprojected", "ecoregions")

    # delete irrelevant ecoregions
    ecoregion_layer = PROJECT.mapLayersByName('ecoregionsReprojected')[0]
    ecoregion_layer.startEditing()
    for ecoregion in ecoregion_layer.getFeatures():
        if (not re.match("9\.([234])", ecoregion['NA_L2CODE'])):
            ecoregion_layer.deleteFeature(ecoregion.id())
    ecoregion_layer.commitChanges()

    # Split ecoregions into north and south
    line = LineString([(180, LATITUDE), (-180, LATITUDE)])
    line_gdf = gpd.GeoDataFrame(pd.DataFrame({'a': ['x']}), geometry=[line], crs='EPSG:4326')
    line_gdf.to_file(DIR_PATH + "/latitude line/latLine.shp", driver="ESRI Shapefile")
    add_or_replace_v_layer(DIR_PATH + "/latitude line/latLine.shp", "latLine")
    line_layer = PROJECT.mapLayersByName('latLine')[0]
    processing.run("native:splitwithlines", {
        'INPUT': ecoregion_layer,
        'LINES': line_layer,
        'OUTPUT': DIR_PATH + "/ecoregionFiles/splitNS.shp"
    })
    add_or_replace_v_layer(DIR_PATH + "/ecoregionFiles/splitNS.shp", "ecoregionsSplitNS", "ecoregionsReprojected")
    # Label each region as north or south
    splitLayer = PROJECT.mapLayersByName('ecoregionsSplitNS')[0]
    splitLayer.startEditing()
    splitLayer.addAttribute(QgsField("NS", QVariant.Double))
    splitLayer.updateFields()
    for region in splitLayer.getFeatures():
        ns = (region.geometry().centroid().asPoint().y() > LATITUDE)
        region.setAttribute("NS", QVariant(True) if ns else QVariant(False))
        splitLayer.updateFeature(region)
    splitLayer.commitChanges()


# def labelStiationsWithEcoregions():
#     #Add ecoregions field to stations
#     processing.run("native:joinattributesbylocation", 
#     {'INPUT': dirPath + '/stationFiles/stationsGdf.shp',
#     'PREDICATE':[5],'JOIN':dirPath + "/ecoregionFiles/reprojected.shp",
#     'JOIN_FIELDS':['NA_L2CODE'],
#     'METHOD':1,
#     'DISCARD_NONMATCHING':False,
#     'PREFIX':'',
#     'OUTPUT':dirPath + '/stationFiles/stationsWithEcoregions.shp'})
#     addOrReplaceVLayer(dirPath + '/stationFiles/stationsWithEcoregions.shp', "stationsGdf", "stationsWithEcoregions")


def calculateAverageSpi():
    # For loops for all the differernt variations
    # TODO, LOAD THIS LAYER IF NOT ALREADY
    stationLayer = PROJECT.mapLayersByName('stationsGdf')[0]
    stationLayer.startEditing()
    # Using 1,2,3 month rolling average data provided
    for rollingLength in range(1, 4):
        spiDf = pd.read_pickle(DIR_PATH + "/spiDf-rollingMonths" + str(rollingLength))
        currentAdress = DIR_PATH + '/ecoregionFiles/splitNS.shp'
        # We will calculate each years average from a variety of start months to end months
        for startMonth in range(1, 8):
            for endMonth in range(startMonth, 8):
                # Looking across years from 2019 to 2023
                for year in range(2019, 2024):
                    attribute = MONTHS[startMonth - 1] + "-" + MONTHS[endMonth - 1] + "|" + str(
                        year - 2000) + "_" + str(rollingLength)
                    stationLayer.addAttribute(QgsField(attribute, QVariant.Double))

                    start_date = pd.to_datetime(str(year) + "-" + str(startMonth), format='%Y-%m')
                    end_date = pd.to_datetime(str(year) + "-" + str(endMonth), format='%Y-%m')
                    boundedSpiDf = spiDf.loc[:, (spiDf.columns >= start_date) & (spiDf.columns <= end_date)]

                    # each station gets its average spi for each variation added to its attribute table
                    for station in stationLayer.getFeatures():
                        qvariant_double = QVariant(float(boundedSpiDf.loc[station['Station']].mean()))
                        station[attribute] = qvariant_double
                        stationLayer.updateFeature(station)

                    # An interpolation is created to fill in the areas between attributes
                    attributeIdx = stationLayer.fields().indexOf(attribute)
                    processing.run("qgis:idwinterpolation",
                                   {'INTERPOLATION_DATA': DIR_PATH + '/stationFiles/stationsGdf.shp::~::0::~::' + str(
                                       attributeIdx) + '::~::0',
                                    'DISTANCE_COEFFICIENT': 99,
                                    'EXTENT': '-116.038827519,-89.618012962,28.596182276,54.486221541 [EPSG:4326]',
                                    'PIXEL_SIZE': 0.5,
                                    'OUTPUT': DIR_PATH + '/interpolatedSpi/' + attribute + ".tif"})
                    # addOrReplaceRLayer(dirPath + '/interpolatedSpi/'+ attribute + ".tif", attribute, attribute)

                    # Average spi is calculated within each ecoregion polygon
                    nextAdress = DIR_PATH + '/ecoregionFiles/ecoregions' + attribute + '.shp'
                    processing.run("native:zonalstatisticsfb",
                                   {'INPUT': currentAdress,
                                    'INPUT_RASTER': DIR_PATH + '/interpolatedSpi/' + attribute + '.tif',
                                    'RASTER_BAND': 1,
                                    'COLUMN_PREFIX': attribute,
                                    'STATISTICS': [2],
                                    'OUTPUT': nextAdress})
                    # addOrReplaceVLayer(nextAdress, attribute, attribute)
                    currentAdress = DIR_PATH + '/ecoregionFiles/ecoregions' + attribute + '.shp'
        add_or_replace_v_layer(currentAdress, 'ecoregionsWithAverages' + str(rollingLength), 'ecoregionsSplitNS')
    stationLayer.commitChanges()


def prepareAndPlot(layerName):
    # make a dataframe out of layer data
    layer = PROJECT.mapLayersByName(layerName)[0]
    fieldnames = [field.name() for field in layer.fields()]
    attributes = []
    for f in layer.getFeatures():
        attrs = f.attributes()
        attributes.append(attrs)
    df = pd.DataFrame(attributes)
    df.columns = fieldnames
    df = df.drop(['NA_L1CODE', 'NA_L1NAME', 'NA_L2KEY', 'NA_L1KEY', 'Shape_Leng'], axis=1)

    # Define a function to calculate the weighted average
    def weighted_average(toMerge):
        areas = toMerge['Shape_Area']
        justAverages = toMerge.drop(['Shape_Area', 'NA_L2CODE', 'NA_L2NAME', 'NS'], axis=1)
        downscaled = justAverages.mul(areas, axis=0)
        summed = downscaled.sum()
        upscaled = summed.div(areas.sum())
        return upscaled

    # Group by the first two columns and apply the weighted average function
    ogRegions = df.groupby(['NA_L2NAME'], as_index=False).apply(weighted_average)
    nsRegions = df.groupby(['NS'], as_index=False).apply(weighted_average)

    graphSets = {}
    graphSets['Temperate Praries'] = ogRegions[ogRegions['NA_L2NAME'] == 'TEMPERATE PRAIRIES']
    graphSets['West Central Praries'] = ogRegions[ogRegions['NA_L2NAME'] == 'WEST-CENTRAL SEMIARID PRAIRIES']
    graphSets['South Central Praries'] = ogRegions[ogRegions['NA_L2NAME'] == 'SOUTH CENTRAL SEMIARID PRAIRIES']
    graphSets['Northern Praries'] = nsRegions[nsRegions['NS'] == QVariant(True)]
    graphSets['Southern Praries'] = nsRegions[nsRegions['NS'] == QVariant(False)]

    for set in graphSets:
        thisSet = graphSets[set]
        thisSet = thisSet.drop(thisSet.columns[0], axis=1).melt()
        timeFrames = thisSet['variable'].str.split('-|\|', expand=True)
        timeFrames.columns = ['Start Month', "End Month", 'Year']
        timeFrames['Year'] = timeFrames['Year'].str.split('_', expand=True)[0]
        thisSet = pd.concat([timeFrames, thisSet['value']], axis=1)
        thisSet = thisSet.pivot(columns='Year', index=['Start Month', 'End Month'], values='value')
        fig, axs = plt.subplots(7, 7, sharex=True, sharey=True, figsize=(20, 20))
        for index, row in thisSet.iterrows():
            axs[int(index[0]) - 1, int(index[1]) - 1].plot(row)
            axs[int(index[0]) - 1, int(index[1]) - 1].set_title(
                "Annual SPI based on months " + index[0] + "-" + index[1], fontsize=10)
            axs[int(index[0]) - 1, int(index[1]) - 1].set_xlabel("Year: 2019-2023", fontsize=8)
            axs[int(index[0]) - 1, int(index[1]) - 1].set_ylabel("Average Spi", fontsize=8)
        plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05, wspace=0.4, hspace=0.6)
        plt.suptitle("Annual SPIs in the " + set + " Region, Calculated With " + layerName[-1] + " Month SPI Data")
        plt.savefig(DIR_PATH + '/final plots/' + set + " using " + layerName[-1] + "  month(s) SPI data" + '.png')


# cleanData()
# calculateAverageSpi()
prepareAndPlot("ecoregionsWithAverages1")
prepareAndPlot("ecoregionsWithAverages2")
prepareAndPlot("ecoregionsWithAverages3")
