import streamlit as st
import pandas as pd 
import numpy as np
import os

def app():
    st.title('Sheep Success Rates by GMU')

    os.chdir('/home/scott/python/adfg/data')
    df = pd.read_csv('sheep_compiled.csv')

    #years = [2010,2011,2012,2013,2014,2015,2016,2017,2018]
    #df_recent = df[df['year'].isin(years)]
    df_recent = df[df['hunted']=='Y']

    g = df_recent.groupby(['hunt','year'])

    df_sort=g.apply(lambda x: (x.killed.value_counts()/len(x))).to_frame()
    df_sort.reset_index(inplace=True)


    #Sidebar
    #change to multiselect?
    gmu_select = st.sidebar.selectbox("Hunt", df_sort.hunt.unique())

    year_select = st.sidebar.slider('Year',
                                    min_value=int(df_sort.year.unique().min()),
                                    max_value=int(df_sort.year.unique().max()),
                                    value=(int(df_sort.year.unique().min()),int(df_sort.year.unique().max())))

    year_comp = st.sidebar.number_input('Compare GMUs since', min_value=1979, max_value=2017, value=2010)


    #Filter Dataframe
    df_temp=df_sort[(df_sort.year >= year_select[0]) & 
                    (df_sort.year <= year_select[1]) & 
                    (df_sort.hunt == gmu_select)]

    st.dataframe(df_temp, width=900, height = 500)

    df_temp= df_temp[df_temp['level_2']=='Y'] #level 2 is killed Y or No
    df_temp.drop(['hunt','level_2'],axis=1,inplace=True)
    df_temp = df_temp.rename(columns={'year':'index'}).set_index('index')

    st.line_chart(df_temp)

    #https://medium.com/@u.praneel.nihar/building-multi-page-web-app-using-streamlit-7a40d55fa5b4

    #Create df with average kill% for last 10 years

    df_ten = df_sort[df_sort['year']>=year_comp]
    df_ten= df_ten[df_ten['level_2']=='Y']
    df_ten = df_ten.groupby(['hunt'])['killed'].mean()
    df_ten.sort_values(inplace=True, ascending=False)

    st.write(f"Average Hunter Success since {year_comp}")
    st.table(df_ten)