import os 
import re
import pandas as pd
from shapely.geometry import LineString
import geopandas as gpd
import numpy as np
from PyQt5.QtCore import QVariant
import matplotlib.pyplot as plt

project = QgsProject.instance()
dirPath = "/Users/nathanchou/Desktop/2024SummerResearch"

#Helper Functions
def deleteLayer(layerName):
    for layer in project.mapLayers().values():
        if layer.name() == layerName:
            project.removeMapLayer(layer)

#TODO. Should return, and should have optional replace parameter
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

def setupStations():
    
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

    

def findStationAverages(startMonth, endMonth):
     stationLayer = project.mapLayersByName('stationsGdf')[0]
     stationLayer.startEditing()
     # Using 1,2,3 month rolling average data provided
     for rollingLength in range(1,4):
         spiDf = pd.read_pickle(dirPath + "/spiDf-rollingMonths"+str(rollingLength))
         #currentAdress = dirPath + '/ecoregionFiles/' + 'ecoregions07-07|23_' + str(rollingLength)+ ".shp"

         # Looking across years from 2019 to 2023
         for year in range(2019, 2024):
            attribute = str(startMonth) + '-' + str(endMonth) + "|" + str(year-2000)+ '_'+ str(rollingLength)
            print(attribute)
            stationLayer.addAttribute(QgsField(attribute, QVariant.Double))

            start_date = pd.to_datetime(str(year) + "-" + str(startMonth), format='%Y-%m')
            end_date = pd.to_datetime(str(year) + "-" + str(endMonth), format='%Y-%m')
            boundedSpiDf = spiDf.loc[:, (spiDf.columns >= start_date) & (spiDf.columns <= end_date)]
                    
            # each station gets its average spi for each variation added to its attribute table
            for station in stationLayer.getFeatures():
                    qvariant_double = QVariant(float(boundedSpiDf.loc[station['Station']].mean()))
                    station[attribute] = qvariant_double
                    stationLayer.updateFeature(station)
                    
            #An interpolation is created to fill in the areas between attributes
            attributeIdx = stationLayer.fields().indexOf(attribute)
            processing.run("qgis:idwinterpolation", 
            {'INTERPOLATION_DATA':dirPath + '/stationFiles/stationsGdf.shp::~::0::~::'+str(attributeIdx)+'::~::0',
            'DISTANCE_COEFFICIENT':99,
            'EXTENT':'-137.043934002,-76.934285399,23.663691151,71.018365538 [EPSG:4326]',
            'PIXEL_SIZE':0.5,
            'OUTPUT':dirPath + '/Ebird Region Approach/spi files/'+ attribute + ".tif"})
            #addOrReplaceRLayer(dirPath + '/Ebird Region Approach/api files/'+ attribute + ".tif", attribute, attribute)
     stationLayer.commitChanges()
                    
def scaleAbundance(layerName, fid):
    processing.run("native:zonalstatisticsfb", 
             {'INPUT':dirPath + '/Ebird Region Approach/range files/lecspa_range.gpkg',
             'INPUT_RASTER':dirPath + '/Ebird Region Approach/abundance files/'+ layerName +'.tif',
             'RASTER_BAND':1,
             'COLUMN_PREFIX':layerName,
             'STATISTICS':[2],
             'OUTPUT':dirPath + '/Ebird Region Approach/range files/range w mean '+layerName+'.shp'})

    addOrReplaceVLayer(dirPath + '/Ebird Region Approach/range files/range w mean '+layerName+'.shp', 'temp', 'temp')

    myLayer = project.mapLayersByName('temp')[0]
    feature = next(myLayer.getFeatures(QgsFeatureRequest().setFilterFid(fid-1)))
    average = feature[layerName[:10]]
    print(average)
   
    

    processing.run("native:rastercalc", 
                {'LAYERS':[dirPath + '/Ebird Region Approach/abundance files/'+ layerName +'.tif'],
                'EXPRESSION':'"'+ layerName + '@1" / ' + str(average),
                'EXTENT':None,
                'CELL_SIZE':None,
                'CRS':QgsCoordinateReferenceSystem('EPSG:4326'),
                'OUTPUT':dirPath + '/Ebird Region Approach/abundance files/' + layerName + "scaled.tif"})
    


def multiplyWithAbundance(startMonth, endMonth, layerName):
     for rollingLength in range(1,4):
         spiDf = pd.read_pickle(dirPath + "/spiDf-rollingMonths"+str(rollingLength))
         for year in range(2019, 2024):
             attribute = str(startMonth) + '-' + str(endMonth) + "|" + str(year - 2000) + '_'+ str(rollingLength)
             processing.run("native:rastercalc", 
                {'LAYERS':[dirPath + '/Ebird Region Approach/abundance files/'+ layerName +'.tif',dirPath + '/Ebird Region Approach/spi files/'+ attribute + ".tif"],
                'EXPRESSION':'"'+ layerName + '@1" * "' + attribute + '@1"',
                'EXTENT':None,
                'CELL_SIZE':None,
                'CRS':QgsCoordinateReferenceSystem('EPSG:4326'),
                'OUTPUT':dirPath + '/Ebird Region Approach/spi and abundance files/'+ attribute + "_abundance_adjusted.tif"})


def calculateAverage(startMonth, endMonth): 
    currentAdress = dirPath + '/Ebird Region Approach/range files/lecspa_range.gpkg'
    for rollingLength in range(1,4):
         for year in range(2019, 2024):
             attribute = str(startMonth) + '-' + str(endMonth) + "|" + str(year-2000) + '_'+ str(rollingLength)
             nextAdress = dirPath + '/Ebird Region Approach/range files/range_averages_'+ attribute+'.shp'
             processing.run("native:zonalstatisticsfb", 
             {'INPUT':currentAdress,
             'INPUT_RASTER':dirPath + '/Ebird Region Approach/spi and abundance files/'+ attribute + "_abundance_adjusted.tif",
             'RASTER_BAND':1,
             'COLUMN_PREFIX':attribute,
             'STATISTICS':[2],
             'OUTPUT':nextAdress})
             currentAdress = nextAdress
    addOrReplaceVLayer(currentAdress, 'ranges', "ranges with Averages" + str(startMonth) + "-" + str(endMonth) )


def plot(layerName, fid, season):

    #make a dataframe out of layer data
    layer = project.mapLayersByName(layerName)[0]
    fieldnames = [field.name() for field in layer.fields()]
    attributes = []
    for f in layer.getFeatures():
        attrs = f.attributes()
        attributes.append(attrs)
    df = pd.DataFrame(attributes)
    df.columns = fieldnames
    df = df[df['fid'] == fid]
    df = df.drop(['fid', 'species_co', 'scientific', 'common_nam', 'prediction', 'type',
       'season', 'start_date', 'end_date',], axis = 1).melt()
    timeFrames = df['variable'].str.split('-|\||_', expand = True)
    timeFrames.columns = ['Start Month', "End Month", 'Year', 'SPI Months']
    timeFrames['SPI Months'] = timeFrames['SPI Months'].str[0]
    timeFrames = timeFrames.drop(['Start Month',"End Month"], axis = 1)
    df = pd.concat([timeFrames, df['value']], axis = 1)

    fig, axs = plt.subplots(3, 1, sharex=True, sharey=True, figsize=(3.5, 8.5))   
    for i in range(1,4):
        toPlot = df[df['SPI Months'] == str(i)]
        axs[i-1].plot(toPlot['Year'], toPlot['value'])
        axs[i-1].set_title("Using " + str(i) +" Month SPI", fontsize=10)
        axs[i-1].set_xlabel("Year: 2019-2023", fontsize=10)
        axs[i-1].set_ylabel("Average Spi", fontsize=10)
    plt.subplots_adjust(left=0.2, right=0.9, top=0.9, bottom=0.05, wspace=0.4, hspace=0.3)
    plt.suptitle("Annual SPI in "+ season + " range, \n during " + season +" season")
    plt.savefig(dirPath + '/Ebird Region Approach/final plots/' + season + '.png')
    


#addOrReplaceVLayer(dirPath + '/Ebird Region Approach/lecspa_range.gpkg', 'ranges', 'ranges')
# addOrReplaceRLayer(dirPath + '/Ebird Region Approach/breedingAbundance.tif', 'breedingAbundance', 'breedingAbundance')
# addOrReplaceRLayer(dirPath + '/Ebird Region Approach/postBreedingAbundance.tif', 'postBreedingAbundance', 'postBreedingAbundance')
# setupStations()
# findStationAverages(6,8)
# findStationAverages(9,11)
#gdal.SetConfigOption('GDAL_PAM_ENABLED', 'NO')
#scaleAbundance('breedingAbundance', 1)
#scaleAbundance('postBreedingAbundance', 3)
#multiplyWithAbundance(6,8,'breedingAbundancescaled')
#multiplyWithAbundance(9,11,'postBreedingAbundancescaled')

calculateAverage(6,8)
calculateAverage(9,11)

plot('ranges with Averages6-8', 1, 'breeding')
plot('ranges with Averages9-11', 3, 'post-breeding')


