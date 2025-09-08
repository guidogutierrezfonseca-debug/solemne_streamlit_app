import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt

st.set_page_config(page_title="Solemne II", layout="wide")

st.markdown(
    """
    <h1 style='text-align: center;'>Análisis de datos públicos</h1>
    <p style='text-align: right; font-size: 16px;'>
        Fuente: <a href='https://datos.gob.cl/' target='_blank'>datos.gob.cl</a>
    </p>
    """,
    unsafe_allow_html=True
)

if "df" not in st.session_state:
    st.session_state.df = None

@st.cache_data(show_spinner=False)
def fetch_ckan(resource_id: str, q: str = "", limit: int = 100, offset: int = 0) -> pd.DataFrame:
    url = "https://datos.gob.cl/api/3/action/datastore_search"
    params = {"resource_id": resource_id, "limit": int(limit), "offset": int(offset)}
    if q:
        params["q"] = q

    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    payload = r.json()
    records = payload.get("result", {}).get("records", [])
    df = pd.DataFrame(records)

    if df.empty:
        return df
    df.columns = pd.Index(df.columns.map(str))
    df.columns = (
        df.columns.str.strip()
                  .str.replace(r"\s+", "_", regex=True)
                  .str.replace(r"[^0-9a-zA-Z_]", "", regex=True)
                  .str.lower()
    )
    return df

with st.sidebar:
    st.header("Conexión a la API")
    resource_id = st.text_input(
        "resource_id (CKAN)", 
        value="3f862478-3d6b-4d77-a34a-e46732b672f8",  
        key="rid"
    )
    q = st.text_input("Filtro rápido (q)", key="q")
    limit = st.slider("Límite de filas", 10, 5000, 500, step=10, key="limit")
    offset = st.number_input("Offset", min_value=0, value=0, step=100, key="offset")

    sample_rows = st.slider("Muestra (head)", 5, 50, 10, key="sample")
    chart_type = st.selectbox("Tipo de gráfico", ["Conteo por categoría", "Serie temporal"], key="chart")

    run = st.button("Consultar API", type="primary", key="fetch")

if run:
    if not resource_id:  
        st.warning("Debes ingresar un resource_id.")
        st.stop()

    with st.spinner("Consultando datos.gob.cl..."):
        df = fetch_ckan(
            resource_id,
            q=q,
            limit=limit,
            offset=offset
        )

    if df.empty:
        st.warning("Sin datos. Revisa el resource_id o filtros.")
        st.stop()
    else:
        st.session_state.df = df
        st.session_state.last_rid = resource_id
        st.success(f"Datos recibidos: {len(df)} filas × {df.shape[1]} columnas")



if st.session_state.df is None:
    st.info("💡 Ingresa un resource_id y presiona **Consultar API** para habilitar tablas y gráficos.")
    
    st.markdown(
        """
        <hr>
        <p style='text-align: center; font-size:14px; color: gray;'>
            Desarrollado por <b>Guido Gutiérrez Fonseca</b>
        </p>
        """,
        unsafe_allow_html=True
    )
    st.stop()

df = st.session_state.df 


st.subheader("Vista rápida")
st.dataframe(df.head(sample_rows))
st.download_button(
    "Descargar CSV (filtrado)",
    df.to_csv(index=False).encode("utf-8"),
    file_name="datos_filtrados.csv",
    mime="text/csv",
)

st.subheader("Esquema y tipos")
st.write(pd.DataFrame({
    "columna": df.columns,
    "dtype": [str(dt) for dt in df.dtypes],
    "nulos": [int(df[c].isna().sum()) for c in df.columns]
}))

if chart_type == "Conteo por categoría":
    st.subheader("Gráfico por categoría: X=texto, Y=valor numérico")
    cat_cols = [c for c in df.columns if df[c].dtype == "object" or df[c].dtype.name == "category"]
    if not cat_cols:
     st.info("No hay columnas categóricas detectadas.")
    else:
        x_col = st.selectbox("Columna X (categórica)", sorted(cat_cols), key="xy_x")
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        convertible = []
        for c in df.columns:
            if c in num_cols or c == x_col:
                continue
            sample = (
                df[c].astype(str)
                     .str.replace(r"[^\d,.\-]", "", regex=True)  
                     .str.replace(",", ".", regex=False)        
            )
            try:
                pd.to_numeric(sample, errors="raise")
                convertible.append(c)
            except Exception:
                pass
        y_candidates = sorted(list(dict.fromkeys(num_cols + convertible)))
        if not y_candidates:
            st.info("No hay columnas numéricas disponibles.")
            st.stop()
        y_col = st.selectbox("Columna Y (numérica)", y_candidates, key="xy_y")

        combine = st.selectbox("Cómo combinar filas por categoría", ["Tomar primer valor", "Sumar", "Promediar"], key="xy_combine")

        top_n = st.slider("Top N", 5, 50, 10, key="xy_topn")
        order_desc = st.checkbox("Ordenar descendente", value=True, key="xy_desc")

        df_num = df.copy()
        cleaned = (
            df_num[y_col].astype(str)
                         .str.replace(r"[^\d,.\-]", "", regex=True)
                         .str.replace(",", ".", regex=False)
        )
        df_num[y_col] = pd.to_numeric(cleaned, errors="coerce")

        if combine == "Tomar primer valor":
            s = (
                df_num.dropna(subset=[y_col])
                      .drop_duplicates(subset=[x_col], keep="first")
                      .set_index(x_col)[y_col]
            )
        elif combine == "Sumar":
            s = df_num.groupby(x_col)[y_col].sum()
        else:  
            s = df_num.groupby(x_col)[y_col].mean()
        s = s.sort_values(ascending=not order_desc).head(top_n)
        if s.empty:
            st.warning("No hay datos para graficar con esa combinación.")
        else:
            fig, ax = plt.subplots(figsize=(8, 4))
            s.plot(kind="bar", ax=ax)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col if combine == "Tomar primer valor" else f"{combine} de {y_col}")
            ax.set_title(f"{y_col} por {x_col} ({combine})")
            st.pyplot(fig)

else:
    st.subheader("Gráfico: serie temporal / agrupado (X e Y seleccionables)")
    x_col = st.selectbox("Columna para eje X (texto o fecha)", list(df.columns), key="gx_x")
    is_date = False
    try:
        pd.to_datetime(df[x_col], errors="raise")
        is_date = True
    except Exception:
        pass
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    convertible = []
    for c in df.columns:
        if c in num_cols or c == x_col:
            continue
        sample = (
            df[c].astype(str)
                 .str.replace(r"[^\d,.\-]", "", regex=True)
                 .str.replace(",", ".", regex=False)
        )
        try:
            pd.to_numeric(sample, errors="raise")
            convertible.append(c)
        except Exception:
            pass
    y_candidates = sorted(list(dict.fromkeys(num_cols + convertible)))

    y_col = st.selectbox("Columna Y (numérica)", ["(solo conteo)"] + y_candidates, key="gx_y")
    if is_date:
        freq = st.selectbox("Frecuencia (si X es fecha)", ["D", "W", "M"], index=0, key="gx_freq")
    if (not is_date) and (y_col != "(solo conteo)"):
        combine = st.selectbox("Cómo combinar filas por categoría", 
                               ["Tomar primer valor", "Sumar", "Promediar"], key="gx_combine")
    else:
        combine = None
    if not is_date:
        top_n = st.slider("Top N", 5, 50, 10, key="gx_topn")
        order_desc = st.checkbox("Ordenar descendente", value=True, key="gx_desc")
    sdf = df.copy()
    if y_col != "(solo conteo)":
        cleaned = (
            sdf[y_col].astype(str)
                      .str.replace(r"[^\d,.\-]", "", regex=True)
                      .str.replace(",", ".", regex=False)
        )
        sdf[y_col] = pd.to_numeric(cleaned, errors="coerce")
    if is_date:
        sdf[x_col] = pd.to_datetime(sdf[x_col], errors="coerce", infer_datetime_format=True)
        sdf = sdf.dropna(subset=[x_col]).sort_values(x_col)
    if y_col == "(solo conteo)":
        if is_date:
            series = sdf.groupby(pd.Grouper(key=x_col, freq=freq)).size().rename("conteo")
            y_label = "Conteo"
            title_y = "conteo"
        else:
            series = sdf[x_col].astype(str).value_counts()
            y_label = "Conteo"
            title_y = "conteo"
    else:
        if is_date:
            series = sdf.groupby(pd.Grouper(key=x_col, freq=freq))[y_col].sum().rename(y_col)
            y_label = f"Suma de {y_col}"
            title_y = y_col
        else:
            if combine == "Tomar primer valor":
                series = (
                    sdf.dropna(subset=[y_col])
                       .drop_duplicates(subset=[x_col], keep="first")
                       .set_index(x_col)[y_col]
                )
            elif combine == "Sumar":
                series = sdf.groupby(x_col)[y_col].sum()
            else:  
                series = sdf.groupby(x_col)[y_col].mean()
            y_label = (f"{combine} de {y_col}") if combine else y_col
            title_y = y_col
    if series.empty:
        st.warning("No hay datos agregables con esa combinación.")
    else:
        if is_date:
            fig, ax = plt.subplots(figsize=(8, 4))
            series.plot(ax=ax)
            ax.set_xlabel("Fecha"); ax.set_ylabel(y_label)
            ax.set_title(f"Serie temporal ({title_y}) [{freq}]")
            st.pyplot(fig)
        else:  
            series = series.sort_values(ascending=not order_desc).head(top_n)
            fig, ax = plt.subplots(figsize=(8, 4))
            series.plot(kind="bar", ax=ax)
            ax.set_xlabel(x_col); ax.set_ylabel(y_label)
            ax.set_title(f"{title_y} por {x_col}" if y_col != "(solo conteo)" else f"Conteo por {x_col}")
            st.pyplot(fig)

st.markdown(
    """
    <hr>
    <p style='text-align: center; font-size:14px; color: gray;'>
        Desarrollado por <b>Guido Gutiérrez Fonseca</b>
    </p>
    """,
    unsafe_allow_html=True
)
