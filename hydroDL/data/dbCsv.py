""" 
read and extract data from CSV database
"""
import os
import numpy as np
import pandas as pd
import time
import datetime as dt

from .dataframe import Dataframe
import hydroDL.utils as utils

varTarget = ['SMAP_AM']
varForcing = [
    'APCP_FORA', 'DLWRF_FORA', 'DSWRF_FORA', 'TMP_2_FORA', 'SPFH_2_FORA',
    'VGRD_10_FORA', 'UGRD_10_FORA'
]
varConst = [
    'Bulk', 'Capa', 'Clay', 'NDVI', 'Sand', 'Silt', 'flag_albedo',
    'flag_extraOrd', 'flag_landcover', 'flag_roughness', 'flag_vegDense',
    'flag_waterbody'
]


class DataframeCsv(Dataframe):
    def __init__(self, rootDB, *, subset, tRange):
        self.rootDB = rootDB
        self.subset = subset
        rootName, crd, indSub, indSkip = readDBinfo(
            rootDB=rootDB, subset=subset)
        self.crd = crd
        self.indSub = indSub
        self.indSkip = indSkip
        self.rootName = rootName
        # (gridY, gridX, indY, indX) = utils.grid.crd2grid(crd[:, 0], crd[:, 1])
        # self.crdGrid = (gridY, gridX)
        # self.crdGridInd = np.stack((indY, indX), axis=1)
        self.time = utils.time.t2dtLst(tRange[0], tRange[1])

    def getGeo(self):
        return self.crd

    def getT(self):
        return self.time

    def getData(self, *, varT=[], varC=[], doNorm=True, rmNan=True):
        if type(varT) is str:
            varT = [varT]
        if type(varC) is str:
            varC = [varC]

        yrLst, tDb = t2yrLst(self.time)
        indDb, ind = utils.time.intersect(tDb, self.time)
        nt = len(tDb)
        ngrid = len(self.indSub)
        nvar = 0
        for var in [varT, varC]:
            nvar = nvar + len(var)
        data = np.ndarray([ngrid, nt, nvar])

        # time series
        k = 0
        for var in varT:
            dataTemp = readDataTS(
                rootDB=self.rootDB,
                rootName=self.rootName,
                indSub=self.indSub,
                indSkip=self.indSkip,
                yrLst=yrLst,
                fieldName=var)
            if doNorm is True:
                dataTemp = transNorm(
                    dataTemp, rootDB=self.rootDB, fieldName=var)
            data[:, :, k] = dataTemp
            k = k + 1

        # const
        for var in varC:
            dataTemp = readDataConst(
                rootDB=self.rootDB,
                rootName=self.rootName,
                indSub=self.indSub,
                indSkip=self.indSkip,
                yrLst=yrLst,
                fieldName=var)
            if doNorm is True:
                dataTemp = transNorm(
                    dataTemp, rootDB=self.rootDB, fieldName=var, isConst=True)
            data[:, :, k] = np.repeat(
                np.reshape(dataTemp, [ngrid, 1]), nt, axis=1)
            k = k + 1

        if rmNan is True:
            data[np.where(np.isnan(data))] = 0
        dataOut = data[:, indDb, :]
        return dataOut


def t2yrLst(tArray):
    t1 = tArray[0]
    t2 = tArray[-1]
    y1 = t1.year
    y2 = t2.year
    if t1 < dt.datetime(y1, 4, 1):
        y1 = y1 - 1
    if t2 < dt.datetime(y2, 4, 1):
        y2 = y2 - 1
    yrLst = list(range(y1, y2 + 1))
    tDb = utils.time.t2dtLst(dt.datetime(y1, 4, 1), dt.datetime(y2 + 1, 4, 1))
    return yrLst, tDb


def readDBinfo(*, rootDB, subset):
    subsetFile = os.path.join(rootDB, "Subset", subset + ".csv")
    print(subsetFile)
    dfSubset = pd.read_csv(subsetFile, dtype=np.int64, header=0)
    rootName = dfSubset.columns.values[0]
    indSub = dfSubset.values.flatten()

    crdFile = os.path.join(rootDB, rootName, "crd.csv")
    crdRoot = pd.read_csv(crdFile, dtype=np.float, header=None).values

    indAll = np.arange(0, crdRoot.shape[0], dtype=np.int64)
    if np.array_equal(indSub, np.array([-1])):
        indSub = indAll
        indSkip = None
    else:
        indSub = indSub - 1
        indSkip = np.delete(indAll, indSub)
    crd = crdRoot[indSub, :]
    return rootName, crd, indSub, indSkip


def readDBtime(*, rootDB, rootName, yrLst):
    tnum = np.empty(0, dtype=np.datetime64)
    for yr in yrLst:
        timeFile = os.path.join(rootDB, rootName, str(yr), "timeStr.csv")
        temp = (pd.read_csv(timeFile, dtype=str, header=None).astype(
            np.datetime64).values.flatten())
        tnum = np.concatenate([tnum, temp], axis=0)
    return tnum


def readVarLst(*, rootDB, varLst):
    varFile = os.path.join(rootDB, "Variable", varLst + ".csv")
    varLst = pd.read_csv(
        varFile, header=None, dtype=str).values.flatten().tolist()
    return varLst


def readDataTS(*, rootDB, rootName, indSub, indSkip, yrLst, fieldName):
    tnum = readDBtime(rootDB=rootDB, rootName=rootName, yrLst=yrLst)
    nt = len(tnum)
    ngrid = len(indSub)

    # read data
    data = np.zeros([ngrid, nt])
    k1 = 0
    for yr in yrLst:
        t1 = time.time()
        dataFile = os.path.join(rootDB, rootName, str(yr), fieldName + ".csv")
        dataTemp = pd.read_csv(
            dataFile, dtype=np.float, skiprows=indSkip, header=None).values
        k2 = k1 + dataTemp.shape[1]
        data[:, k1:k2] = dataTemp
        k1 = k2
        print("read " + dataFile, time.time() - t1)
    data[np.where(data == -9999)] = np.nan
    return data


def readDataConst(*, rootDB, rootName, indSub, indSkip, yrLst, fieldName):
    # read data
    dataFile = os.path.join(rootDB, rootName, "const", fieldName + ".csv")
    data = pd.read_csv(
        dataFile, dtype=np.float, skiprows=indSkip,
        header=None).values.flatten()
    data[np.where(data == -9999)] = np.nan
    return data


def readStat(*, rootDB, fieldName, isConst=False):
    if isConst is False:
        statFile = os.path.join(rootDB, "Statistics", fieldName + "_stat.csv")
    else:
        statFile = os.path.join(rootDB, "Statistics",
                                "const_" + fieldName + "_stat.csv")
    stat = pd.read_csv(statFile, dtype=np.float, header=None).values.flatten()
    return stat


def transNorm(data, *, rootDB, fieldName, fromRaw=True, isConst=False):
    stat = readStat(rootDB=rootDB, fieldName=fieldName, isConst=isConst)
    if fromRaw is True:
        dataOut = (data - stat[2]) / stat[3]
    else:
        dataOut = data * stat[3] + stat[2]
    return (dataOut)
