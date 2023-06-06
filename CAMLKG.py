import io
import json
import math
import os
import sqlite3
import sys
from pathlib import Path
from sqlite3 import Error
from urllib.parse import urljoin

import folium
import geopandas as gpd
import matplotlib.image as mpimg
import numpy as np
import pandas as pd
import pyqtgraph as pg
import requests
from bs4 import BeautifulSoup
from folium import GeoJson
from PyQt6 import QtCore, QtGui, QtWidgets, uic
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import (QColor, QDesktopServices, QPixmap, QStandardItem,
                         QStandardItemModel)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox,
                             QStyledItemDelegate, QTableView, QVBoxLayout,
                             QWidget)


class LinkDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return None

    def editorEvent(self, event, model, option, index):
        if event.type() == event.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            column = index.column()
            if column == 0:
                item = model.itemFromIndex(index)
                href = item.data(Qt.ItemDataRole.UserRole)
                if href:
                    QDesktopServices.openUrl(QUrl(href))
                    return True
        return super().editorEvent(event, model, option, index)

class TableModel(QtCore.QAbstractTableModel):
 
    def __init__(self, data):
        super(TableModel, self).__init__()
        self._data = data
 
    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()] #pandas's iloc method
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:          
            return Qt.AlignmentFlag.AlignVCenter + Qt.AlignmentFlag.AlignHCenter
        if role == Qt.ItemDataRole.BackgroundRole and (index.row()%2 == 0):
            return QtGui.QColor('#F7E9F3')
 
    def rowCount(self, index):
        return self._data.shape[0]
 
    def columnCount(self, index):
        return self._data.shape[1]
 
    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal and section < self._data.shape[1]:
                return str(self._data.columns[section])
            elif orientation == Qt.Orientation.Vertical and section < self._data.shape[0]:
                return str(self._data.index[section])
            else:
                return None
            
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        uic.loadUi('./CAMLKG.ui', self)
        self.show()
        self.tabWidget.setCurrentIndex(0)
        # create a database connect
        database = './CAMLKG.db'
        self.conn = create_connection(database)
        self.setWindowTitle('Judgement Visualize System')
        self.SecondWindow = SecondWindow(self)
        self.NewsWindow = NewsWindow(self)
        items = fetch_jid(self.conn)
        jid_items = set()
        for item in items:
            if item[0] is not None:
                jid_items.add(str(item[0]))
        self.JID_combo.addItems(list(jid_items)) # set 物件需要轉換成 list 物件才能被添加到 self.JID_combo
        self.JID_combo.setCurrentIndex(-1)

        
        # items = fetch_year(self.conn)
        # year_items = set()
        # for item in items:
        #     if item[0] is not None:
        #         year_items.add(str(item[0]))
        # self.year_combo.addItems(list(year_items))
        self.year_combo.setToolTip("Tip: You must select one Year to search.")
        self.year_combo.setCurrentIndex(-1)

        style_sheet = '''
            QTextBrowser {
                background-color: transparent;
                border: 2px dashed gray;
                border-radius: 10px;
            }
        '''

        self.textBrowser.setStyleSheet(style_sheet)
        self.textBrowser_2.setStyleSheet(style_sheet)

        # Taiwan's Map
        # f = open('./geo_taiwan_short.json',encoding='utf8')
        # self.data = json.load(f)
        # self.show_map()

        self.search_btn.clicked.connect(self.open_new_window)
        self.exit_btn.clicked.connect(self.showExitDialog)
        self.exit_btn_2.clicked.connect(self.showExitDialog)
        self.comboBox_page.activated.connect(self.showTable) # activated 是當選單有被點擊時才觸發
        self.JID_combo.activated.connect(self.searchByJID)
        self.tableView.doubleClicked.connect(self.Visualize)
        # self.plot_widget.setBackground('transparent')
        self.year_combo.activated.connect(self.getStatistics)
        self.year_combo.activated.connect(self.show_map)
        
        self.pushButton_first.clicked.connect(self.firstPage)
        self.pushButton_last.clicked.connect(self.lastPage)
        self.pushButton_previous.clicked.connect(self.previousPage)
        self.pushButton_next.clicked.connect(self.nextPage)
        self.GoSearch_btn.clicked.connect(self.goSearch)
        self.news_btn.clicked.connect(self.open_news_window)

    def open_news_window(self):
        # self.NewsWindow = SecondWindow(self)
        self.NewsWindow.news()
        self.NewsWindow.show()

    def open_new_window(self):
        if self.JID_combo.currentIndex() == -1:
            QMessageBox.warning(self, "Warning", "Please select a JID!")
        else:
            self.SecondWindow = SecondWindow(self)
            self.SecondWindow.update_KG_view()
            self.SecondWindow.urlBrowser()
            self.SecondWindow.show()
        
    def showExitDialog(self):
        choice = QMessageBox.question(self, 'Exit Dialog', 'Are you sure to exit?')
        if choice == QMessageBox.StandardButton.Yes:
            self.conn.close() # close database
            self.close() # close app

    def goSearch(self):
        self.tabWidget.setCurrentIndex(1)

    def searchByJID(self):
        jid_str = str(self.JID_combo.currentText())
        sql = f"SELECT * FROM caml A WHERE A.JID='{jid_str}'"
        with self.conn:
            self.rows = SQLExecute(self, sql)
            if len(self.rows) > 0: 
                ToTableView(self, self.rows)

    def showTable(self):
        page = int(self.comboBox_page.currentText())
        start_idx = (page - 1) * 10
        end_idx = start_idx + 10
        data = self.df.iloc[start_idx:end_idx, :]
        self.model = TableModel(data)
        self.tableView.setModel(self.model)

    def Visualize(self, mi):
        # Fetch data from the SQLite database
        col_list = list(self.df.columns)
        jid = self.df.iloc[mi.row(), col_list.index('JID')]
        self.cur = self.conn.cursor()
        self.cur.execute(f"SELECT * FROM caml WHERE JID = ?", (jid,))
        # Update the SecondWindow's KG view
        self.SecondWindow = SecondWindow(self)
        self.SecondWindow.update_KG_view()
        self.SecondWindow.show()

    def getStatistics(self):
        year = self.year_combo.currentText()
        if year == '107':
            sql = "SELECT * FROM '107'"
        elif year == '108':
            sql = "SELECT * FROM '108'"
        elif year == '109':
            sql = "SELECT * FROM '109'"
        elif year == '110':
            sql = "SELECT * FROM '110'"

        with self.conn:
            self.rows = SQLExecute(self, sql)
        self.df = pd.DataFrame(self.rows, columns=['City/County', 'Count', 'CountySN'])

        Dataset = self.df
        json_file_path = r'./geo_taiwan_short.json'
        # 讀入台灣行政區地理資料並取行政區名稱與界線經緯度
        geojson = gpd.read_file(json_file_path, encoding='utf-8')
        geojson=geojson[['name','geometry']]
        # 整合人口數資料與行政區地理資料為單一 pandas 變數
        self.df_final = geojson.merge(Dataset, left_on="name", right_on="City/County", how="outer") 
        self.df_final = self.df_final[~self.df_final['geometry'].isna()]
        with open(json_file_path, 'r', encoding='utf-8') as j:
            self.geo_taiwan = json.loads(j.read())

        # Bar Chart
        # color_map = {'新北市': 'b','台北市': 'g','桃園市': 'r','台中市': 'c','台南市': 'm','高雄市': 'y','宜蘭縣': 'k','新竹縣': 'b','苗栗縣': 'g',
        #             '彰化縣': 'r','南投縣': 'c','雲林縣': 'm','嘉義縣': 'y','屏東縣': 'k','台東縣': 'b','花蓮縣': 'g','澎湖縣': 'r','基隆市': 'c','新竹市': 'm',
        #             '嘉義市': 'y','金門縣': 'k','連江縣': 'b'}

        # x = np.arange(len(self.df['City/County']))
        # y = np.array(self.df['Count'])
        # colors = [color_map.get(city, 'gray') for city in self.df['City/County']]

        # 建立BarGraphItem並將其添加到PlotWidget中
        # bar_graph = pg.BarGraphItem(x=x, height=y, width=0.6, brushes=colors)
        # self.plot_widget = pg.PlotWidget()
        # self.plot_widget.setFixedSize(800, 600)
        # self.plot_widget.addItem(bar_graph)

        # 設定圖形標題和軸標籤
        # self.plot_widget.setTitle('Count of Judgements by City/County')
        # self.plot_widget.setLabel('left', 'Count')
        # self.plot_widget.setLabel('bottom', 'City/County')

        # 顯示圖形
        # self.plot_widget.show()
        # styles = {'color':'black', 'font-size':'11px'}
        # self.plot_widget.setLabel('left', 'Count', **styles)
        # self.plot_widget.setLabel('bottom', 'City/Country', **styles)

    def show_map(self):
        # 刪除上一次選擇的地圖
        while self.verticalLayout_2.count():
            item = self.verticalLayout_2.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        current_dir = Path(__file__).resolve().parent
        m = folium.Map(location=[23.73, 120.96], zoom_start=7)
        folium.Choropleth(
                geo_data = self.geo_taiwan,#Assign geo_data to your geojson file
                name = "choropleth",
                data = self.df_final,#Assign dataset of interest
                columns = ["City/County","Count"],#Assign columns in the dataset for plotting
                key_on = 'feature.properties.name',#Assign the key that geojson uses to connect with dataset
                fill_color = 'YlOrRd',
                fill_opacity = 0.7,
                line_opacity = 0.5,
                reset=True,
                legend_name = '臺灣縣市加密貨幣洗錢相關判決數量').add_to(m)
         
        folium.GeoJson(
                data=self.df_final, #Dataset merged from pandas and geojson
                name='Count',
                smooth_factor=2,
                style_function=lambda x: {'color':'black','fillColor':'transparent','weight':0.1},
                tooltip=folium.GeoJsonTooltip(
                       fields=['City/County',
                                'Count'
                               ],
                       aliases=['行政區',
                                '判決數'
                                ], 
                        localize=True,
                        sticky=False,
                        labels=True,
                        style="""
                            background-color: #F0EFEF;
                            border: 2px solid black;
                            border-radius: 3px;
                            box-shadow: 3px;
                        """,
                        max_width=800),
                highlight_function=lambda x: {'weight':3,'fillColor':'grey'},
                        ).add_to(m) 
 
        data = io.BytesIO()
        m.save(data, close_file = False)
        filename = os.fspath(current_dir / "map.html")
        m.save(filename)
        webView = QWebEngineView()  # a QWidget
        webView.setHtml(data.getvalue().decode()) # html size < 2M
 
        self.verticalLayout_2.addWidget(webView, 0) # at position 0

    def firstPage(self):
            try:
                page = int(1)
                if self.comboBox_page.currentText() == str(page):
                    QMessageBox.warning(self, "Warning", "This is already the first page!")
                else:
                    self.comboBox_page.setCurrentText(str(page))
                    start_idx = (page - 1) * 10
                    end_idx = start_idx + 10
                    data = self.df.iloc[start_idx:end_idx, :]
                    self.model = TableModel(data)
                    self.tableView.setModel(self.model)
            except:
                QMessageBox.warning(self, "Warning", "No result!")

    def lastPage(self):
        try:
            page = int(self.comboBox_page.itemText(self.comboBox_page.count() - 1))
            if self.comboBox_page.currentText() == str(page):
                    QMessageBox.warning(self, "Warning", "This is already the last page!")
            else:
                self.comboBox_page.setCurrentText(str(page))
                start_idx = (page - 1) * 10
                end_idx = start_idx + 10
                data = self.df.iloc[start_idx:end_idx, :]
                self.model = TableModel(data)
                self.tableView.setModel(self.model)
        except:
            QMessageBox.warning(self, "Warning", "No result!")
        
    def previousPage(self):
        try:
            page = int(self.comboBox_page.currentText())
            first_page = int(1)
            if page == first_page:
                QMessageBox.warning(self, "Warning", "This is already the first page!")
            else:
                start_idx = (page - 2) * 10
                end_idx = start_idx + 10
                data = self.df.iloc[start_idx:end_idx, :]
                self.model = TableModel(data)
                self.tableView.setModel(self.model)
                page = self.comboBox_page.setCurrentText(str(int(self.comboBox_page.currentText())-1))
        except:
            QMessageBox.warning(self, "Warning", "No result!")

    def nextPage(self):
        try:
            page = int(self.comboBox_page.currentText())
            last_page = int(self.comboBox_page.itemText(self.comboBox_page.count() - 1))
            if page == last_page:
                QMessageBox.warning(self, "Warning", "This is already the last page!") 
            else:
                start_idx = (page) * 10
                end_idx = start_idx + 10
                data = self.df.iloc[start_idx:end_idx, :]
                self.model = TableModel(data)
                self.tableView.setModel(self.model)
                page = self.comboBox_page.setCurrentText(str(int(self.comboBox_page.currentText())+1))
        except: 
            QMessageBox.warning(self, "Warning", "No result!")

class SecondWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=MainWindow):
        super(SecondWindow, self).__init__(parent)
        uic.loadUi('./KG_visual.ui', self)
        self.tabWidget.setCurrentIndex(0)
        database = './CAMLKG.db'
        # create a database connect
        self.conn = create_connection(database)
        self.setWindowTitle('Judgement Visualize System')
        self.parent = parent
        self.urlBrowser()
        self.back_btn.clicked.connect(self.backToMainWindow)
        self.back_btn_2.clicked.connect(self.backToMainWindow)

    def update_KG_view(self):
        jid = str(self.parent.JID_combo.currentText())
        self.KG_label.setText(f'Knowledge Graph of "{jid}"')
        # img_path = u"./images/" + jid + ".png"
        # pixmap = QPixmap(img_path)
        # image = pixmap.toImage()
        # scaled_image = image.scaled(self.KG_view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        # scaled_pixmap = QPixmap.fromImage(scaled_image)
        # self.KG_view.setPixmap(scaled_pixmap)
        # self.KG_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.graphWidget.setBackground('transparent')
        self.graphWidget.clear()
        img_dir = "./images/"
        img_name = jid + ".png"
        image = mpimg.imread(img_dir + img_name)
        img_item = pg.ImageItem(image, axisOrder='row-major')
         
        self.graphWidget.addItem(img_item)
        self.graphWidget.invertY(True)
        self.graphWidget.getAxis('bottom').setTicks('')
        self.graphWidget.getAxis('left').setTicks('')
        self.graphWidget.setAspectLocked(lock=True, ratio=1)

    def urlBrowser(self):
        url = 'https://judgment.judicial.gov.tw/FJUD/default.aspx'
        webView2 = QWebEngineView()
        webView2.load(QUrl(url))
         
        # clear the current widget in the verticalLayout before adding one
        if self.judicial_web.itemAt(0) : # if any existing widget
            self.judicial_web.itemAt(0).widget().setParent(None)
         
        self.judicial_web.addWidget(webView2)
        

    def backToMainWindow(self):
        self.conn.close() # close database
        self.close() # close app
        main = MainWindow()
        main.show()

class NewsWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=MainWindow):
        super(NewsWindow, self).__init__(parent)
        uic.loadUi('./news.ui', self)
        self.setWindowTitle('News of Courts')
        self.parent = parent

    def news(self):
        url = "https://www.judicial.gov.tw/tw/lp-1888-1.html"
        response = requests.get(url)
        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table", class_="table_sprite")
        table_view = self.findChild(QtWidgets.QTableView, 'news_table')
        model = table_view.model()
        if model is None:
            model = QStandardItemModel()
            table_view.setStyleSheet("background-color: transparent; alternate-background-color: #F7E9F3;")
            table_view.setModel(model)

        header_labels = ["Title", "Post Date", "Unit/Organization"]
        model.setHorizontalHeaderLabels(header_labels)

        table_rows = table.find_all("tr")
        for row in table_rows[1:16]:
            cells = row.find_all("td")
            row_data = [cell.get_text(strip=True) for cell in cells]
            item = [QStandardItem(data) for data in row_data]
            del item[0]

            href = cells[1].find("a").get("href")
            abs_href = urljoin(url, href)
            print(abs_href)
            item[0].setData(abs_href, Qt.ItemDataRole.UserRole)
            model.appendRow(item)

        # 設定tableView屬性
        table_view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table_view.horizontalHeader().setStretchLastSection(True)
        table_view.resizeColumnsToContents()
        # table_view.setColumnWidth(0, 50)
        table_view = self.findChild(QtWidgets.QTableView, 'news_table')

        delegate = LinkDelegate(table_view)
        table_view.setItemDelegateForColumn(0, delegate)  # 修改這裡的索引為 0

    # def news_page(self):
    #     url = 'https://judgment.judicial.gov.tw/FJUD/default.aspx'
    #     webView3 = QWebEngineView()
    #     webView3.load(QUrl(url))
         
    #     # clear the current widget in the verticalLayout before adding one
    #     if self.news_page.itemAt(0) : # if any existing widget
    #         self.news_page.itemAt(0).widget().setParent(None)
         
    #     self.news_page.addWidget(webView3)
        

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)
 
    return conn

def SQLExecute(self, SQL):
    self.cur = self.conn.cursor()
    self.cur.execute(SQL)
    rows = self.cur.fetchall()

    if len(rows) == 0 and SQL != '': # nothing found
        # raise a messageBox here
        dlg = QMessageBox(self)
        # dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setWindowTitle("SQL Information: ")
        dlg.setText("No data match the query!")
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes)
        buttonY = dlg.button(QMessageBox.StandardButton.Yes)
        buttonY.setText('OK')
        dlg.setIcon(QMessageBox.Icon.Information)
        button = dlg.exec()
        # return
    return rows

def ToTableView(self, rows):
    self.comboBox_page.clear()
    names = [description[0] for description in self.cur.description] # extract column names
    self.df = pd.DataFrame(rows)
    self.model = TableModel(self.df)
    self.tableView.setModel(self.model)
    self.df.columns = names
    self.df.index = range(1, len(rows)+1)
    self.lineEdit_total.setText(str(len(rows)))
    self.comboBox_page.addItems(list(map(str, range(1, math.ceil(len(rows)/10)+1))))

    page = 0
    start_idx = (page) * 10
    end_idx = start_idx + 10
    data = self.df.iloc[start_idx:end_idx, :]
    self.model = TableModel(data)
    self.tableView.setModel(self.model)


def exit():
    app = QtWidgets.QApplication(sys.argv) #sys.argv
    sys.exit(app.exec())

def fetch_jid(conn):
    cur = conn.cursor()
    sql = "select jid from caml"
    cur.execute(sql)
    rows = cur.fetchall()
    return rows

def fetch_year(conn):
    cur = conn.cursor()
    sql = "select year from caml"
    cur.execute(sql)
    rows = cur.fetchall()
    return rows

def main():
    database = './CAMLKG.db' # 建立與數據庫的連接
    conn = create_connection(database)
    conn.close()
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())
 
if __name__ == '__main__':
    main()
