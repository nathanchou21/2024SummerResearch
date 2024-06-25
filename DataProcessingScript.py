import os 
import re
import pandas as pd
from shapely.geometry import LineString
import geopandas as gpd
import numpy as np
from PyQt5.QtCore import QVariant
import matplotlib.pyplot as plt

project = QgsProject.instance()
#TODO make this look at where the code is running once I stop running from the python console 
dirPath = "/Users/nathanchou/Desktop/2024SummerResearch"
originalDataPath = dirPath + "/originalData"
months = [ "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
latitude = 42.305

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

    #delete irrelevant ecoregions
    ecoregionLayer = project.mapLayersByName('ecoregionsReprojected')[0]
    ecoregionLayer.startEditing()
    for ecoregion in ecoregionLayer.getFeatures():
        if (not re.match("9\.(2|3|4)", ecoregion['NA_L2CODE'])):
            ecoregionLayer.deleteFeature(ecoregion.id())
    ecoregionLayer.commitChanges()
            
    #Split ecoregions into north and south
    line = LineString([(180, latitude), (-180, latitude)])
    lineGdf = gpd.GeoDataFrame(pd.DataFrame({'a': ['x']}), geometry=[line], crs='EPSG:4326')
    lineGdf.to_file(dirPath + "/latitude line/latLine.shp", driver="ESRI Shapefile")
    addOrReplaceVLayer(dirPath + "/latitude line/latLine.shp", "latLine", "latLine")
    lineLayer = project.mapLayersByName('latLine')[0]
    processing.run("native:splitwithlines", {
    'INPUT': ecoregionLayer,
    'LINES': lineLayer,
    'OUTPUT': dirPath + "/ecoregionFiles/splitNS.shp"
    })
    addOrReplaceVLayer(dirPath + "/ecoregionFiles/splitNS.shp", "ecoregionsReprojected", "ecoregionsSplitNS")
    #Label each region as north or south
    splitLayer = project.mapLayersByName('ecoregionsSplitNS')[0]
    splitLayer.startEditing()
    splitLayer.addAttribute(QgsField("NS", QVariant.Double))
    splitLayer.updateFields()
    for region in splitLayer.getFeatures():
        ns = (region.geometry().centroid().asPoint().y() > latitude)
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
    
    #For loops for all the differernt variations
    stationLayer = project.mapLayersByName('stationsGdf')[0]
    stationLayer.startEditing()
    # Using 1,2,3 month rolling average data provided
    for rollingLength in range(1,4):
        spiDf = pd.read_pickle(dirPath + "/spiDf-rollingMonths"+str(rollingLength))
        #currentAdress = dirPath +'/ecoregionsWithAverages' + str(rollingLength)
        currentAdress = dirPath + '/ecoregionFiles/' + 'ecoregions07-07|23_' + str(rollingLength)+ ".shp"
        #We will calculate each years average from a variety of start months to end months
        for startMonth in range(1,8):
            for endMonth in range(8,12):
                # Looking across years from 2019 to 2023
                for year in range(2019, 2024):
                    attribute = months[startMonth-1] + "-" + months[endMonth-1]+ "|"+str(year-2000)+"_" + str(rollingLength)
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
                    {'INTERPOLATION_DATA':dirPath + '/stationFiles/stationsGdf.shp::~::0::~::'+str(attributeIdx)+'::~::0',
                    'DISTANCE_COEFFICIENT':99,
                    'EXTENT':'-116.038827519,-89.618012962,28.596182276,54.486221541 [EPSG:4326]',
                    'PIXEL_SIZE':0.5,
                    'OUTPUT':dirPath + '/interpolatedSpi/'+ attribute + ".tif"})
                    #addOrReplaceRLayer(dirPath + '/interpolatedSpi/'+ attribute + ".tif", attribute, attribute)

                    # Average spi is calculated within each ecoregion polygon
                    nextAdress = dirPath + '/ecoregionFiles/ecoregions'+ attribute+'.shp'
                    processing.run("native:zonalstatisticsfb", 
                    {'INPUT':currentAdress,
                    'INPUT_RASTER':dirPath + '/interpolatedSpi/' + attribute+ '.tif',
                    'RASTER_BAND':1,
                    'COLUMN_PREFIX':attribute,
                    'STATISTICS':[2],
                    'OUTPUT':nextAdress})
                    #addOrReplaceVLayer(nextAdress, attribute, attribute)
                    currentAdress = dirPath + '/ecoregionFiles/ecoregions'+attribute+'.shp'
        addOrReplaceVLayer(currentAdress, 'ecoregionsSplitNS', 'ecoregionsWithAverages' + str(rollingLength))
    stationLayer.commitChanges()
                    



        
def prepareAndPlot(layerName):

    #make a dataframe out of layer data
    layer = project.mapLayersByName(layerName)[0]
    fieldnames = [field.name() for field in layer.fields()]
    attributes = []
    for f in layer.getFeatures():
        attrs = f.attributes()
        attributes.append(attrs)
    df = pd.DataFrame(attributes)
    df.columns = fieldnames
    df = df.drop(['NA_L1CODE', 'NA_L1NAME', 'NA_L2KEY', 'NA_L1KEY', 'Shape_Leng'], axis = 1)

    

    # Define a function to calculate the weighted average
    def weighted_average(toMerge):
        areas = toMerge['Shape_Area']
        justAverages = toMerge.drop(['Shape_Area', 'NA_L2CODE', 'NA_L2NAME', 'NS'], axis = 1)
        downscaled = justAverages.mul(areas, axis = 0)
        summed = downscaled.sum()
        upscaled = summed.div(areas.sum())
        return upscaled
    


    # Group by the first two columns and apply the weighted average function
    ogRegions = df.groupby(['NA_L2NAME'], as_index = False).apply(weighted_average)
    nsRegions = df.groupby(['NS'], as_index = False).apply(weighted_average)
    
    graphSets = {}
    graphSets['Temperate Prairies'] = ogRegions[ogRegions['NA_L2NAME'] == 'TEMPERATE PRAIRIES']
    graphSets['West Central Prairies']= ogRegions[ogRegions['NA_L2NAME'] == 'WEST-CENTRAL SEMIARID PRAIRIES']
    graphSets['South Central Prairies'] = ogRegions[ogRegions['NA_L2NAME'] == 'SOUTH CENTRAL SEMIARID PRAIRIES']
    graphSets['Northern Prairies'] = nsRegions[nsRegions['NS'] == QVariant(True)]
    graphSets['Southern Prairies'] = nsRegions[nsRegions['NS'] == QVariant(False)]

    for set in graphSets: 
         thisSet = graphSets[set]
         thisSet = thisSet.drop(thisSet.columns[0], axis = 1).melt()
         timeFrames = thisSet['variable'].str.split('-|\|', expand = True)
         timeFrames.columns = ['Start Month', "End Month", 'Year']
         timeFrames['Year'] = timeFrames['Year'].str.split('_', expand = True)[0]
         thisSet = pd.concat([timeFrames, thisSet['value']], axis = 1)
         thisSet = thisSet.pivot(columns = 'Year', index = ['Start Month', 'End Month'], values = 'value')
         thisSet.to_csv(dirPath + "/final csv files/" + set + '_' + layerName[-1] + " month spi")
         fig, axs = plt.subplots(12, 12, sharex=True, sharey=True, figsize=(30, 20))
         for index, row in thisSet.iterrows():
            axs[int(index[0])-1,int(index[1])-1].plot(row)
            axs[int(index[0])-1,int(index[1])-1].set_title("Annual SPI based on months " + index[0] + "-" + index[1], fontsize=10)
            axs[int(index[0])-1,int(index[1])-1].set_xlabel("Year: 2019-2023", fontsize=8)
            axs[int(index[0])-1,int(index[1])-1].set_ylabel("Average Spi", fontsize=8)
         plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05, wspace=0.4, hspace=0.6)
         plt.suptitle("Annual SPIs in the " + set + " Region, Calculated With " +  layerName[-1] +" Month SPI Data")
         plt.savefig(dirPath + '/final plots/' + set + " using " +  layerName[-1] +"  month(s) SPI data" + '.png')



#cleanData()
calculateAverageSpi()
prepareAndPlot("ecoregionsWithAverages1")
prepareAndPlot("ecoregionsWithAverages2")
prepareAndPlot("ecoregionsWithAverages3")




#import matplotlib.pyplot as plt
#
## Data from the table
#years = [2019, 2020, 2021, 2022, 2023]
#west_central_semi_arid = [0.2722, -0.3139, -0.3976, -0.4371, -0.1968]
#northern = [0.0797, -0.4107, -0.5129, -0.1845, -0.0498]
#southern = [0.6345, -0.1785, 0.1612, -0.4113, -0.3797]
#
## Plotting the data
#plt.figure(figsize=(10, 6))
#plt.plot(years, west_central_semi_arid, marker='o', label='West-Central Semi-Arid')
#plt.plot(years, northern, marker='o', label='Northern')
#plt.plot(years, southern, marker='o', label='Southern')
#
## Adding titles and labels
#plt.title('Mean 1 Month Standardized Precipitation Index From Mar to Jun')
#plt.xlabel('Year')
#plt.ylabel('Precipitation Index')
#plt.legend()
#plt.grid(True)
#plt.xticks(years)
#
## Display the plot
#plt.show()


# import matplotlib.pyplot as plt
# import pandas as pd

# eBirdDf =pd.read_csv('/Users/nathanchou/Desktop/2024SummerResearch/originalData/eBirdData.csv', delimiter = "	")
# eBirdDf = eBirdDf[['individualCount', 'decimalLatitude', 'decimalLongitude', 'day', 'month', 'year', 'scientificName']]
# yearCountsAll = eBirdDf[['individualCount', 'year']].groupby('year').sum()
# print(yearCounts)
# print (eBirdDf['scientificName'].head())
# justLeConteDf = eBirdDf[eBirdDf['scientificName'] == 'Ammospiza leconteii (Audubon, 1844)']
# yearCountsLeConte = justLeConteDf[['individualCount', 'year']].groupby('year').sum()
# print(yearCountsLeConte)
# adjusted = yearCountsLeConte.div(yearCountsAll).mul(100)

# plt.figure(figsize=(10, 6))
# plt.plot(adjusted, marker='o', linestyle='-', color='b')

# plt.title("LeConte's Sparrows as a percentage of EBird observations in Harris County")
# plt.xlabel('Year')
# plt.ylabel('Percentage')
# plt.xticks(adjusted.index)
# plt.grid(True)
# plt.show()



# plt.show()

