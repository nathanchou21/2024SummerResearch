import os 
import pandas as pd
import geopandas as gpd
from PyQt5.QtCore import QVariant


project = QgsProject.instance()
#TODO make this look at where the code is running once I stop running from the python console 
dirPath = "/Users/nathanchou/Desktop/Nathan Chou Summer 2024 Research"
originalDataPath = dirPath + "/originalData"
months = [ "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]

#Helper Functions
def deleteLayer(layerName):
    for layer in project.mapLayers().values():
        if layer.name() == layerName:
            project.removeMapLayer(layer)


def addOrReplaceLayer(path, layerToDelete, layerName, type):
    deleteLayer(layerToDelete)
    deleteLayer(layerName)
    if type == "raster":
        succesful = iface.addRasterLayer(path, layerName, "gdal")
    elif type == "vector":
        succesful = iface.addVectorLayer(path, layerName, "ogr")
    else:
        succesful = False
    if not succesful:
        print(layerName + " layer failed to load!")
        
def addOrReplaceVLayer(path, layerToDelete, layerName):
    addOrReplaceLayer(path, layerToDelete, layerName, 'vector')
    
def addOrReplaceRLayer(path, layerToDelete, layerName):
    addOrReplaceLayer(path, layerToDelete, layerName, 'raster')

def cleanData():
    
    #Creates dataframe with SPI data
    for i in range(1,4):
        canadaDf = pd.read_csv(originalDataPath + '/0' + str(i) + 'mon-spi-cn.csv', header = None, names= ["Station", "ElementCode", "Year"] + months)
        usDf = pd.read_csv(originalDataPath + '/0' + str(i) + 'mon-spi-us.csv', header = None, names= ["Station", "ElementCode", "Year"] + months)
        combinedDf = pd.concat([canadaDf, usDf]).reset_index().drop('index', axis = 1)
        combinedDf = combinedDf[combinedDf['Year'] > 2018].drop(['ElementCode'], axis = 1)
        df_melted = pd.melt(combinedDf, id_vars=["Station", "Year"], var_name="Month", value_name="Spi")
        df_melted["Year_month"] = pd.to_datetime(df_melted["Year"].astype(str) + "-" + df_melted["Month"],format='%Y-%m')
        df_melted = df_melted.sort_values(by = ["Year_month"])
        spiDf = df_melted.pivot(index="Station", columns="Year_month", values="Spi")
        spiDf.to_pickle(dirPath + "/spiDf-rollingMonths"+str(i))

        
    #Creates a dataframe with all the stations and there lat/long locations
    canStationsDf = pd.read_csv(originalDataPath + '/can-metadata.csv', header = None, names= ["Station", "Latitude", "Longitude", "District", "Division", "Drop"])
    canStationsDf = canStationsDf.drop([ "District", "Division", "Drop"], axis = 1)
    usStationsDf = pd.read_csv(originalDataPath + '/us48-div-metadata.csv', header = None, names= ["Station", "Latitude", "Longitude", "District", "Division", "Drop"])
    usStationsDf = usStationsDf.drop([ "District", "Division", "Drop"], axis = 1)
    stationsDf = pd.concat([usStationsDf, canStationsDf]).reset_index().drop('index', axis = 1)
    oneMonthDf = pd.read_pickle(dirPath + "/spiDf-rollingMonths1")
    stationsDf = stationsDf[stationsDf['Station'].isin(oneMonthDf.index.to_series().values)]
    
    #Creates a shape file from this dataframe
    stationLocs = gpd.points_from_xy(stationsDf.Longitude, stationsDf.Latitude)
    stationsGdf = gpd.GeoDataFrame(stationsDf.Station, geometry=stationLocs)
    stationsGdf.to_file(dirPath + '/stationFiles/stationsGdf.shp', driver = "Shapefile", crs=4326)


    #display stations and ecoregions
    addOrReplaceVLayer(dirPath + '/stationFiles/stationsGdf.shp', "stationsGdf", "stationsGdf")
    addOrReplaceVLayer(originalDataPath + '/na_cec_eco_l2/NA_CEC_Eco_Level2.shp', "ecoregions", "ecoregions")

    #reproject ecoregions
    processing.run("native:reprojectlayer", 
    {'INPUT': originalDataPath + '/na_cec_eco_l2/NA_CEC_Eco_Level2.shp',
    'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:4326'),
    'CONVERT_CURVED_GEOMETRIES':False,
    'OPERATION':'+proj=pipeline +step +inv +proj=laea +lat_0=45 +lon_0=-100 +x_0=0 +y_0=0 +ellps=sphere +step +proj=unitconvert +xy_in=rad +xy_out=deg',
    'OUTPUT':dirPath + "/ecoregionFiles/reprojected.shp"})
    addOrReplaceVLayer(dirPath + "/ecoregionFiles/reprojected.shp", "ecoregions", "ecoregionsReprojected")

def labelStiationsWithEcoregions():
    #Add ecoregions field to stations
    processing.run("native:joinattributesbylocation", 
    {'INPUT': dirPath + '/stationFiles/stationsGdf.shp',
    'PREDICATE':[5],'JOIN':dirPath + "/ecoregionFiles/reprojected.shp",
    'JOIN_FIELDS':['NA_L2CODE'],
    'METHOD':1,
    'DISCARD_NONMATCHING':False,
    'PREFIX':'',
    'OUTPUT':dirPath + '/stationFiles/stationsWithEcoregions.shp'})
    addOrReplaceVLayer(dirPath + '/stationFiles/stationsWithEcoregions.shp', "stationsGdf", "stationsWithEcoregions")
    

def calculateAverageSpi():
    
    stationLayer = project.mapLayersByName('stationsGdf')[0]
    stationLayer.startEditing()
    #vectorLayer = project.mapLayersByName('ecoregionsReprojected')[0]
    #vectorLayer.startEditing()
    oldAdress = dirPath +'/ecoregionFiles/reprojected.shp'
    for rollingLength in range(1,2):
        spiDf = pd.read_pickle(dirPath + "/spiDf-rollingMonths"+str(rollingLength))
        for startMonth in range(1,2):#len(months)):
            for endMonth in range(4,5):#startmonth, len(months)):

                annualAverage = [] 

                for year in range(2019, 2020):
                    attribute = months[startMonth] + "-" + months[endMonth]+ "|"+str(year-2000)+"_" + str(rollingLength)
                    stationLayer.addAttribute(QgsField(attribute, QVariant.Double))

                    start_date = pd.to_datetime(str(year) + "-" + str(startMonth), format='%Y-%m')
                    end_date = pd.to_datetime(str(year) + "-" + str(endMonth), format='%Y-%m')
                    boundedSpiDf = spiDf.loc[:, (spiDf.columns >= start_date) & (spiDf.columns <= end_date)]
                    
                    
                    for station in stationLayer.getFeatures():
                        qvariant_double = QVariant(float(boundedSpiDf.loc[station['Station']].mean()))
                        station[attribute] = qvariant_double
                        stationLayer.updateFeature(station)
                    
                    attributeIdx = stationLayer.fields().indexOf(attribute)
                    processing.run("qgis:idwinterpolation", 
                    {'INTERPOLATION_DATA':dirPath + '/stationFiles/stationsGdf.shp::~::0::~::'+str(attributeIdx)+'::~::0',
                    'DISTANCE_COEFFICIENT':99,
                    'EXTENT':'-116.038827519,-89.618012962,28.596182276,54.486221541 [EPSG:4326]',
                    'PIXEL_SIZE':0.25,
                    'OUTPUT':dirPath + '/interpolatedSpi/'+ attribute + ".tif"})
                    addOrReplaceRLayer(dirPath + '/interpolatedSpi/'+ attribute + ".tif", attribute, attribute)

                    
                    processing.run("native:zonalstatisticsfb", 
                    {'INPUT':oldAdress,
                    'INPUT_RASTER':dirPath + '/interpolatedSpi/' + attribute+ '.tif',
                    'RASTER_BAND':1,
                    'COLUMN_PREFIX':attribute,
                    'STATISTICS':[2],
                    'OUTPUT':dirPath + '/ecoregionFiles/ecoregionsWithSpis.shp'})
                    addOrReplaceVLayer(dirPath + '/ecoregionFiles/ecoregionsWithSpis.shp', "test", "test")
                    oldAdress = '/Users/nathanchou/Desktop/Nathan Chou Summer 2024 Research/ecoregionFiles/ecoregionsWithSpis.shp'
                    #rasterLayer = project.mapLayersByName(attribute)[0]
                    #zonal_stats = QgsZonalStatistics(vectorLayer, rasterLayer, attribute, QgsZonalStatistics.Mean)
                    #zonal_stats.calculateStatistics(None)
    #vectorLayer.commitChanges()
    #vectorLayer.dataProvider().forceReload()                
    stationLayer.commitChanges()                

#cleanData()
#labelStiationsWithEcoregions()
#calculateAverageSpi()

stationLayer = project.mapLayersByName('stationsGdf')[0]
stationLayer.startEditing()
for year in range(2020, 2021):
     attribute = months[1] + "-" + months[4]+ "|"+str(year-2000)+"_" + str(1)
     stationLayer.addAttribute(QgsField(attribute, QVariant.Double))

     start_date = pd.to_datetime(str(year) + "-" + str(1), format='%Y-%m')
     end_date = pd.to_datetime(str(year) + "-" + str(4), format='%Y-%m')
     spiDf = pd.read_pickle(dirPath + "/spiDf-rollingMonths"+str(1))
     boundedSpiDf = spiDf.loc[:, (spiDf.columns >= start_date) & (spiDf.columns <= end_date)]
    
    
     for station in stationLayer.getFeatures():
         qvariant_double = QVariant(float(boundedSpiDf.loc[station['Station']].mean()))
         station[attribute] = qvariant_double
         stationLayer.updateFeature(station)
    
     attributeIdx = stationLayer.fields().indexOf(attribute)
     processing.run("qgis:idwinterpolation", 
     {'INTERPOLATION_DATA':dirPath + '/stationFiles/stationsGdf.shp::~::0::~::'+str(attributeIdx)+'::~::0',
     'DISTANCE_COEFFICIENT':99,
     'EXTENT':'-116.038827519,-89.618012962,28.596182276,54.486221541 [EPSG:4326]',
     'PIXEL_SIZE':0.25,
     'OUTPUT':dirPath + '/interpolatedSpi/'+ attribute + ".tif"})
     addOrReplaceRLayer(dirPath + '/interpolatedSpi/'+ attribute + ".tif", attribute, attribute)

    
# processing.run("native:zonalstatisticsfb", 
#                     {'INPUT':'/Users/nathanchou/Desktop/Nathan Chou Summer 2024 Research/ecoregionFiles/ecoregionsWithSpis.shp',
#                     'INPUT_RASTER':dirPath + '/interpolatedSpi/' + '02-05|20_1'+ '.tif',
#                     'RASTER_BAND':1,
#                     'COLUMN_PREFIX':'02-05|20_1',
#                     'STATISTICS':[2],
#                     'OUTPUT':dirPath + '/ecoregionFiles/ecoregionsWithSpis.shp'})
#addOrReplaceVLayer(dirPath + '/ecoregionFiles/ecoregionsWithSpis.shp', "test", "test")



