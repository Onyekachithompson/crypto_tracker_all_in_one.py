"""
Cryptocurrency Tracker Application - All-in-One Version
This single file contains all the functionality for tracking cryptocurrencies,
managing portfolios, and analyzing the market.
"""

import streamlit as st
import pandas as pd
import time
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px

# Configure page
st.set_page_config(
    page_title="Crypto Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Base URL for CoinGecko API
BASE_URL = "https://api.coingecko.com/api/v3"

# Cache to store API responses and minimize API calls
CACHE = {}
CACHE_EXPIRY = {}
CACHE_DURATION = 60  # Cache duration in seconds

#############################################
# DATA UTILITY FUNCTIONS
#############################################

def get_with_cache(url, params=None, cache_duration=CACHE_DURATION):
    """
    Makes a GET request with caching to avoid hitting API rate limits.
    
    Args:
        url: The URL to request
        params: URL parameters
        cache_duration: How long to cache the response (in seconds)
        
    Returns:
        JSON response from the API
    """
    cache_key = f"{url}_{str(params)}"
    
    # Check if we have a non-expired cached response
    current_time = time.time()
    if cache_key in CACHE and CACHE_EXPIRY.get(cache_key, 0) > current_time:
        return CACHE[cache_key]
    
    # Make the actual API call if no cache or expired
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        data = response.json()
        
        # Cache the response
        CACHE[cache_key] = data
        CACHE_EXPIRY[cache_key] = current_time + cache_duration
        
        return data
    except requests.exceptions.RequestException as e:
        # Handle API errors gracefully
        print(f"API request error: {e}")
        return None

def get_top_coins(limit=100):
    """
    Get the top cryptocurrencies by market cap.
    
    Args:
        limit: Number of coins to return
        
    Returns:
        List of coin data
    """
    url = f"{BASE_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h,7d"
    }
    
    return get_with_cache(url, params)

def search_coins(query):
    """
    Search for coins by name or symbol.
    
    Args:
        query: Search query string
        
    Returns:
        List of matching coins
    """
    url = f"{BASE_URL}/search"
    params = {"query": query}
    
    return get_with_cache(url, params)

def get_coin_details(coin_id):
    """
    Get detailed information about a specific coin.
    
    Args:
        coin_id: CoinGecko coin ID (e.g., 'bitcoin')
        
    Returns:
        Detailed coin data
    """
    url = f"{BASE_URL}/coins/{coin_id}"
    params = {
        "localization": False, 
        "tickers": False,
        "market_data": True,
        "community_data": False,
        "developer_data": False
    }
    
    return get_with_cache(url, params)

def get_coin_history(coin_id, days='30'):
    """
    Get historical price data for a coin.
    
    Args:
        coin_id: CoinGecko coin ID
        days: Time range in days (1, 7, 14, 30, 90, 180, 365, max)
        
    Returns:
        Historical price data
    """
    url = f"{BASE_URL}/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily" if int(days) > 7 else "hourly"
    }
    
    data = get_with_cache(url, params)
    
    if not data:
        return None
    
    # Process historical data into a DataFrame
    try:
        prices = data.get('prices', [])
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error processing historical data: {e}")
        return None

def get_global_market_data():
    """
    Get global cryptocurrency market data.
    
    Returns:
        Global market data including total market cap, volume, etc.
    """
    url = f"{BASE_URL}/global"
    
    return get_with_cache(url)

def calculate_portfolio_value(holdings):
    """
    Calculate the current value of a crypto portfolio.
    
    Args:
        holdings: Dictionary of {coin_id: amount} holdings
        
    Returns:
        Dictionary with portfolio value and performance metrics
    """
    if not holdings:
        return {"total_value": 0, "holdings": []}
    
    # Get current prices for all coins in the portfolio
    coin_ids = list(holdings.keys())
    all_coins = get_top_coins(250)  # Fetch a large list to ensure we have all needed coins
    
    if not all_coins:
        return {"total_value": 0, "holdings": [], "error": "Failed to fetch coin data"}
    
    # Create a lookup dictionary for prices
    coin_prices = {}
    for coin in all_coins:
        coin_prices[coin['id']] = {
            'current_price': coin.get('current_price', 0),
            'price_change_24h_percentage': coin.get('price_change_percentage_24h', 0),
            'symbol': coin.get('symbol', ''),
            'name': coin.get('name', ''),
            'image': coin.get('image', '')
        }
    
    # Calculate portfolio value
    portfolio_items = []
    total_value = 0
    
    for coin_id, amount in holdings.items():
        if coin_id in coin_prices:
            coin_data = coin_prices[coin_id]
            value = amount * coin_data['current_price']
            total_value += value
            
            portfolio_items.append({
                'id': coin_id,
                'symbol': coin_data['symbol'].upper(),
                'name': coin_data['name'],
                'amount': amount,
                'price': coin_data['current_price'],
                'value': value,
                'price_change_24h': coin_data['price_change_24h_percentage'],
                'image': coin_data['image']
            })
    
    # Sort by value (highest to lowest)
    portfolio_items.sort(key=lambda x: x['value'], reverse=True)
    
    return {
        "total_value": total_value,
        "holdings": portfolio_items
    }

#############################################
# CHART UTILITY FUNCTIONS
#############################################

def create_price_chart(df, coin_name, timeframe='30d'):
    """
    Create an interactive price chart for a cryptocurrency.
    
    Args:
        df: DataFrame with price history
        coin_name: Name of the cryptocurrency
        timeframe: Time period to display
        
    Returns:
        Plotly figure object
    """
    if df is None or df.empty:
        # Return empty chart with message if no data
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig
    
    # Create the price chart
    fig = px.line(
        df, 
        x='date', 
        y='price',
        title=f"{coin_name} Price History ({timeframe})"
    )
    
    # Customize the chart
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Price (USD)",
        hovermode="x unified",
        legend_title_text="",
    )
    
    # Add range slider
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1d", step="day", stepmode="backward"),
                dict(count=7, label="7d", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(step="all")
            ])
        )
    )
    
    # Format y-axis as currency
    fig.update_yaxes(tickprefix="$")
    
    return fig

def create_portfolio_pie_chart(portfolio_data):
    """
    Create a pie chart showing portfolio allocation.
    
    Args:
        portfolio_data: Portfolio data from calculate_portfolio_value()
        
    Returns:
        Plotly figure object
    """
    holdings = portfolio_data.get('holdings', [])
    
    if not holdings:
        # Return empty chart with message if no data
        fig = go.Figure()
        fig.add_annotation(
            text="No portfolio data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig
    
    # Create data for pie chart
    labels = [item['symbol'] for item in holdings]
    values = [item['value'] for item in holdings]
    
    # Create pie chart
    fig = px.pie(
        names=labels,
        values=values,
        title="Portfolio Allocation",
        hole=0.4,  # Create a donut chart
    )
    
    # Customize the chart
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hoverinfo='label+percent+value',
        hovertemplate='%{label}: %{percent} <br>Value: $%{value:.2f}<extra></extra>'
    )
    
    return fig

def create_market_dominance_chart(market_data):
    """
    Create a pie chart showing market dominance of top cryptocurrencies.
    
    Args:
        market_data: Global market data from get_global_market_data()
        
    Returns:
        Plotly figure object
    """
    if not market_data or 'data' not in market_data:
        # Return empty chart with message if no data
        fig = go.Figure()
        fig.add_annotation(
            text="No market data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig
    
    market_cap_percentage = market_data['data'].get('market_cap_percentage', {})
    
    if not market_cap_percentage:
        # Return empty chart with message if no market cap data
        fig = go.Figure()
        fig.add_annotation(
            text="No market dominance data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig
    
    # Sort market cap percentages
    sorted_data = sorted(
        [(k.upper(), v) for k, v in market_cap_percentage.items()],
        key=lambda x: x[1],
        reverse=True
    )
    
    # Take top 8 and group the rest as "Others"
    top_n = 8
    if len(sorted_data) > top_n:
        top_coins = sorted_data[:top_n]
        others_value = sum(v for _, v in sorted_data[top_n:])
        chart_data = top_coins + [("Others", others_value)]
    else:
        chart_data = sorted_data
    
    # Create pie chart data
    labels = [item[0] for item in chart_data]
    values = [item[1] for item in chart_data]
    
    # Create pie chart
    fig = px.pie(
        names=labels,
        values=values,
        title="Market Dominance",
        hole=0.4,  # Create a donut chart
    )
    
    # Customize the chart
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hoverinfo='label+percent',
        hovertemplate='%{label}: %{percent}<extra></extra>'
    )
    
    return fig

def create_price_comparison_chart(coins_data, timeframe='7d'):
    """
    Create a comparison chart of multiple cryptocurrencies.
    
    Args:
        coins_data: Dictionary with coin_id as key and historical data DataFrame as value
        timeframe: Time period displayed
        
    Returns:
        Plotly figure object
    """
    if not coins_data:
        # Return empty chart with message if no data
        fig = go.Figure()
        fig.add_annotation(
            text="No comparison data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig
    
    # Create figure
    fig = go.Figure()
    
    # Process each coin's data
    for coin_id, data in coins_data.items():
        if data is None or data.empty:
            continue
            
        # Normalize prices to percentage change from first value
        first_price = data['price'].iloc[0]
        normalized_prices = [(price / first_price - 1) * 100 for price in data['price']]
        
        # Add line for this coin
        fig.add_trace(
            go.Scatter(
                x=data['date'],
                y=normalized_prices,
                mode='lines',
                name=coin_id.capitalize()
            )
        )
    
    # Customize the chart
    fig.update_layout(
        title=f"Price Comparison ({timeframe})",
        xaxis_title="Date",
        yaxis_title="% Change",
        hovermode="x unified",
        legend_title_text="",
    )
    
    # Format y-axis
    fig.update_yaxes(ticksuffix="%")
    
    return fig

#############################################
# HELPER FUNCTIONS
#############################################

def format_large_number(num):
    """Format large numbers with suffix K, M, B, T"""
    if num is None:
        return "N/A"
    
    if num >= 1_000_000_000_000:
        return f"${num / 1_000_000_000_000:.2f}T"
    elif num >= 1_000_000_000:
        return f"${num / 1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"${num / 1_000_000:.2f}M"
    elif num >= 1_000:
        return f"${num / 1_000:.2f}K"
    else:
        return f"${num:.2f}"

#############################################
# PAGE FUNCTIONS
#############################################

def home_dashboard():
    st.title("Cryptocurrency Dashboard")
    
    # Get top cryptocurrencies
    coins = get_top_coins(50)
    
    if not coins:
        st.error("Failed to fetch cryptocurrency data. Please try again later.")
        return
    
    # Create top metrics row
    st.subheader("Top Cryptocurrencies")
    
    # Display top 3 cryptocurrencies with metrics
    col1, col2, col3 = st.columns(3)
    
    # Display Bitcoin
    bitcoin = next((coin for coin in coins if coin['id'] == 'bitcoin'), None)
    if bitcoin:
        with col1:
            price_change = bitcoin.get('price_change_percentage_24h', 0)
            delta_color = "normal" if price_change == 0 else "inverse" if price_change < 0 else "normal"
            st.metric(
                f"Bitcoin (BTC)",
                f"${bitcoin['current_price']:,.2f}",
                f"{price_change:.2f}%",
                delta_color=delta_color
            )
    
    # Display Ethereum
    ethereum = next((coin for coin in coins if coin['id'] == 'ethereum'), None)
    if ethereum:
        with col2:
            price_change = ethereum.get('price_change_percentage_24h', 0)
            delta_color = "normal" if price_change == 0 else "inverse" if price_change < 0 else "normal"
            st.metric(
                f"Ethereum (ETH)",
                f"${ethereum['current_price']:,.2f}",
                f"{price_change:.2f}%",
                delta_color=delta_color
            )
    
    # Display BNB
    bnb = next((coin for coin in coins if coin['id'] == 'binancecoin'), None)
    if bnb:
        with col3:
            price_change = bnb.get('price_change_percentage_24h', 0)
            delta_color = "normal" if price_change == 0 else "inverse" if price_change < 0 else "normal"
            st.metric(
                f"Binance Coin (BNB)",
                f"${bnb['current_price']:,.2f}",
                f"{price_change:.2f}%",
                delta_color=delta_color
            )
    
    # Create dropdown with coin options
    coin_options = [(coin['id'], f"{coin['name']} ({coin['symbol'].upper()})") for coin in coins]
    
    # Get selected coin (default to Bitcoin)
    default_coin_index = next((i for i, option in enumerate(coin_options) if option[0] == 'bitcoin'), 0)
    selected_coin_id = st.selectbox(
        "Select cryptocurrency", 
        options=[option[0] for option in coin_options],
        index=default_coin_index,
        format_func=lambda x: next((option[1] for option in coin_options if option[0] == x), x)
    )
    
    # Get selected cryptocurrency details
    selected_coin = next((coin for coin in coins if coin['id'] == selected_coin_id), None)
    
    if not selected_coin:
        st.error("Failed to load selected cryptocurrency data.")
        return
    
    # Get more detailed information about the selected coin
    coin_details = get_coin_details(selected_coin_id)
    
    # Display selected coin information
    st.subheader(f"{selected_coin['name']} ({selected_coin['symbol'].upper()}) Details")
    
    # Create metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        price_change = selected_coin.get('price_change_percentage_24h', 0)
        delta_color = "normal" if price_change == 0 else "inverse" if price_change < 0 else "normal"
        st.metric(
            "Current Price",
            f"${selected_coin['current_price']:,.2f}",
            f"{price_change:.2f}%",
            delta_color=delta_color
        )
    
    with col2:
        market_cap = selected_coin.get('market_cap', 0)
        st.metric("Market Cap", f"${market_cap:,.0f}")
    
    with col3:
        volume = selected_coin.get('total_volume', 0)
        st.metric("24h Volume", f"${volume:,.0f}")
    
    with col4:
        if coin_details and 'market_data' in coin_details:
            ath = coin_details['market_data'].get('ath', {}).get('usd', 0)
            st.metric("All-Time High", f"${ath:,.2f}")
    
    # Get historical data for price chart
    timeframe_options = {'1d': '1 Day', '7d': '7 Days', '30d': '30 Days', '90d': '90 Days', '365d': '1 Year', 'max': 'All Time'}
    
    # Create timeframe selector
    selected_timeframe = st.select_slider(
        "Timeframe",
        options=list(timeframe_options.keys()),
        value='30d',
        format_func=lambda x: timeframe_options[x]
    )
    
    # Get historical price data
    historical_data = get_coin_history(
        selected_coin_id, 
        days=selected_timeframe.replace('d', '')
    )
    
    # Create and display price chart
    price_chart = create_price_chart(
        historical_data, 
        selected_coin['name'],
        selected_timeframe
    )
    
    st.plotly_chart(price_chart, use_container_width=True)
    
    # Display additional information about the coin
    if coin_details:
        st.subheader("About")
        
        # Description (if available)
        if 'description' in coin_details and 'en' in coin_details['description']:
            description = coin_details['description']['en']
            if description:
                st.markdown(description)
            else:
                st.info("No description available for this cryptocurrency.")
        
        # Additional metrics
        if 'market_data' in coin_details:
            st.subheader("Additional Metrics")
            
            col1, col2 = st.columns(2)
            
            with col1:
                metrics_data = [
                    ("Circulating Supply", f"{coin_details['market_data'].get('circulating_supply', 0):,.0f} {selected_coin['symbol'].upper()}"),
                    ("Total Supply", f"{coin_details['market_data'].get('total_supply', 0):,.0f} {selected_coin['symbol'].upper()}" if coin_details['market_data'].get('total_supply') else "∞"),
                    ("Max Supply", f"{coin_details['market_data'].get('max_supply', 0):,.0f} {selected_coin['symbol'].upper()}" if coin_details['market_data'].get('max_supply') else "∞"),
                ]
                
                for label, value in metrics_data:
                    st.metric(label, value)
            
            with col2:
                price_change_metrics = [
                    ("Price Change (7d)", f"{coin_details['market_data'].get('price_change_percentage_7d', 0):.2f}%"),
                    ("Price Change (30d)", f"{coin_details['market_data'].get('price_change_percentage_30d', 0):.2f}%"),
                    ("Price Change (1y)", f"{coin_details['market_data'].get('price_change_percentage_1y', 0):.2f}%"),
                ]
                
                for label, value in price_change_metrics:
                    price_change = float(value.strip('%'))
                    delta_color = "normal" if price_change == 0 else "inverse" if price_change < 0 else "normal"
                    st.metric(label, "", value, delta_color=delta_color)
    
    # Top movers section
    st.subheader("Today's Top Movers")
    
    # Filter and sort coins by 24h price change
    top_gainers = sorted(
        [coin for coin in coins if coin.get('price_change_percentage_24h', 0) > 0],
        key=lambda x: x.get('price_change_percentage_24h', 0),
        reverse=True
    )[:5]  # Top 5 gainers
    
    top_losers = sorted(
        [coin for coin in coins if coin.get('price_change_percentage_24h', 0) < 0],
        key=lambda x: x.get('price_change_percentage_24h', 0)
    )[:5]  # Top 5 losers
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Top Gainers")
        
        for coin in top_gainers:
            price_change = coin.get('price_change_percentage_24h', 0)
            st.metric(
                f"{coin['name']} ({coin['symbol'].upper()})",
                f"${coin['current_price']:,.2f}",
                f"{price_change:.2f}%"
            )
    
    with col2:
        st.markdown("#### Top Losers")
        
        for coin in top_losers:
            price_change = coin.get('price_change_percentage_24h', 0)
            st.metric(
                f"{coin['name']} ({coin['symbol'].upper()})",
                f"${coin['current_price']:,.2f}",
                f"{price_change:.2f}%",
                delta_color="inverse"
            )

def portfolio_page():
    st.title("Portfolio Tracker")
    
    # Initialize session state for portfolio if it doesn't exist
    if 'portfolio' not in st.session_state:
        st.session_state.portfolio = {}
    
    # Get top coins for the dropdown
    coins = get_top_coins(250)
    
    if not coins:
        st.error("Failed to fetch cryptocurrency data. Please try again later.")
        return
    
    # Create two columns layout
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.subheader("Add Coin to Portfolio")
        
        # Create dropdown with coin options
        coin_options = [(coin['id'], f"{coin['name']} ({coin['symbol'].upper()})") for coin in coins]
        selected_coin_id = st.selectbox(
            "Select Coin", 
            options=[option[0] for option in coin_options],
            format_func=lambda x: next((option[1] for option in coin_options if option[0] == x), x)
        )
        
        # Amount input
        amount = st.number_input("Amount", min_value=0.0, value=0.0, step=0.01)
        
        # Add button
        if st.button("Add to Portfolio"):
            if amount > 0:
                st.session_state.portfolio[selected_coin_id] = st.session_state.portfolio.get(selected_coin_id, 0) + amount
                st.success(f"Added to portfolio!")
                st.rerun()  # Rerun the app to update the portfolio display
            else:
                st.warning("Please enter an amount greater than 0.")
    
    # Calculate portfolio value
    portfolio_data = calculate_portfolio_value(st.session_state.portfolio)
    
    # Display portfolio summary
    st.subheader("Portfolio Summary")
    st.metric("Total Portfolio Value", f"${portfolio_data['total_value']:.2f}")
    
    # Portfolio allocation chart
    if portfolio_data['holdings']:
        st.plotly_chart(create_portfolio_pie_chart(portfolio_data), use_container_width=True)
    
    # Holdings table
    if portfolio_data['holdings']:
        st.subheader("Your Holdings")
        
        # Prepare data for the table
        holdings_data = []
        for holding in portfolio_data['holdings']:
            holdings_data.append({
                "Coin": holding['name'],
                "Symbol": holding['symbol'],
                "Amount": f"{holding['amount']:.6f}",
                "Price": f"${holding['price']:.2f}",
                "Value": f"${holding['value']:.2f}",
                "24h Change": f"{holding['price_change_24h']:.2f}%",
                "": "Remove"  # Button column
            })
        
        # Convert to DataFrame for display
        df = pd.DataFrame(holdings_data)
        
        # Display table with remove buttons
        for i, row in df.iterrows():
            col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1, 2, 1, 1, 1, 1])
            
            coin_id = next((h['id'] for h in portfolio_data['holdings'] if h['name'] == row['Coin']), None)
            
            with col1:
                st.write(row['Coin'])
            with col2:
                st.write(row['Symbol'])
            with col3:
                st.write(row['Amount'])
            with col4:
                st.write(row['Price'])
            with col5:
                st.write(row['Value'])
            with col6:
                price_change = float(row['24h Change'].strip('%'))
                delta_color = "normal" if price_change == 0 else "inverse" if price_change < 0 else "normal"
                st.metric("", "", delta=row['24h Change'], delta_color=delta_color)
            with col7:
                if st.button("Remove", key=f"remove_{i}"):
                    if coin_id in st.session_state.portfolio:
                        del st.session_state.portfolio[coin_id]
                        st.rerun()
    else:
        st.info("Your portfolio is empty. Add coins to get started!")
    
    # Clear portfolio button
    if st.session_state.portfolio:
        if st.button("Clear Portfolio"):
            st.session_state.portfolio = {}
            st.rerun()

def watchlist_page():
    st.title("Crypto Watchlist")
    
    # Initialize session state for watchlist if it doesn't exist
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    
    # Get top coins for the dropdown
    coins = get_top_coins(250)
    
    if not coins:
        st.error("Failed to fetch cryptocurrency data. Please try again later.")
        return
    
    # Create dropdown with coin options
    coin_options = [(coin['id'], f"{coin['name']} ({coin['symbol'].upper()})") for coin in coins]
    
    # Create two columns for add coin interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_coin_id = st.selectbox(
            "Add coin to watchlist", 
            options=[option[0] for option in coin_options],
            format_func=lambda x: next((option[1] for option in coin_options if option[0] == x), x)
        )
    
    with col2:
        st.write("")
        st.write("")
        if st.button("Add"):
            if selected_coin_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(selected_coin_id)
                st.success(f"Added to watchlist!")
                st.rerun()
            else:
                st.info("This coin is already in your watchlist.")
    
    # Timeframe selection for comparison chart
    timeframe_options = {'1d': '1 Day', '7d': '7 Days', '30d': '30 Days', '90d': '90 Days'}
    selected_timeframe = st.selectbox(
        "Timeframe",
        options=list(timeframe_options.keys()),
        format_func=lambda x: timeframe_options[x],
        index=1  # Default to 7 days
    )
    
    # Get historical data for comparison chart
    comparison_data = {}
    for coin_id in st.session_state.watchlist:
        comparison_data[coin_id] = get_coin_history(coin_id, days=selected_timeframe.replace('d', ''))
    
    # Display comparison chart if we have coins in the watchlist
    if st.session_state.watchlist:
        st.subheader("Price Comparison")
        comparison_chart = create_price_comparison_chart(comparison_data, timeframe=selected_timeframe)
        st.plotly_chart(comparison_chart, use_container_width=True)
    
    # Display watchlist table
    if st.session_state.watchlist:
        st.subheader("Your Watchlist")
        
        # Get current data for watchlist coins
        watchlist_data = []
        for coin in coins:
            if coin['id'] in st.session_state.watchlist:
                watchlist_data.append({
                    "Coin": coin['name'],
                    "Symbol": coin['symbol'].upper(),
                    "Price": f"${coin['current_price']:.2f}",
                    "24h Change": f"{coin.get('price_change_percentage_24h', 0):.2f}%",
                    "7d Change": f"{coin.get('price_change_percentage_7d_in_currency', 0):.2f}%",
                    "Market Cap": f"${coin.get('market_cap', 0):,}",
                    "": "Remove"  # Button column
                })
        
        # Convert to DataFrame for display
        df = pd.DataFrame(watchlist_data)
        
        # Display table with remove buttons
        for i, row in df.iterrows():
            col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1, 1, 1, 1, 2, 1])
            
            coin_id = next((coin['id'] for coin in coins if coin['name'] == row['Coin']), None)
            
            with col1:
                st.write(row['Coin'])
            with col2:
                st.write(row['Symbol'])
            with col3:
                st.write(row['Price'])
            with col4:
                price_change_24h = float(row['24h Change'].strip('%'))
                delta_color = "normal" if price_change_24h == 0 else "inverse" if price_change_24h < 0 else "normal"
                st.metric("", "", delta=row['24h Change'], delta_color=delta_color)
            with col5:
                price_change_7d = float(row['7d Change'].strip('%'))
                delta_color = "normal" if price_change_7d == 0 else "inverse" if price_change_7d < 0 else "normal"
                st.metric("", "", delta=row['7d Change'], delta_color=delta_color)
            with col6:
                st.write(row['Market Cap'])
            with col7:
                if st.button("Remove", key=f"remove_{i}"):
                    if coin_id in st.session_state.watchlist:
                        st.session_state.watchlist.remove(coin_id)
                        st.rerun()
    else:
        st.info("Your watchlist is empty. Add coins to get started!")
    
    # Clear watchlist button
    if st.session_state.watchlist:
        if st.button("Clear Watchlist"):
            st.session_state.watchlist = []
            st.rerun()

def market_page():
    st.title("Cryptocurrency Market")
    
    # Get global market data
    global_data = get_global_market_data()
    
    if not global_data or 'data' not in global_data:
        st.error("Failed to fetch global market data. Please try again later.")
        return
    
    # Get top coins
    coins = get_top_coins(100)
    
    if not coins:
        st.error("Failed to fetch cryptocurrency data. Please try again later.")
        return
    
    # Display global market metrics
    st.subheader("Global Market Metrics")
    
    # Create 3 columns for metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_market_cap = global_data['data'].get('total_market_cap', {}).get('usd')
        st.metric("Total Market Cap", format_large_number(total_market_cap))
    
    with col2:
        total_volume = global_data['data'].get('total_volume', {}).get('usd')
        st.metric("24h Trading Volume", format_large_number(total_volume))
    
    with col3:
        btc_dominance = global_data['data'].get('market_cap_percentage', {}).get('btc', 0)
        st.metric("Bitcoin Dominance", f"{btc_dominance:.2f}%")
    
    # Display market dominance chart
    st.plotly_chart(create_market_dominance_chart(global_data), use_container_width=True)
    
    # Display top cryptocurrencies table
    st.subheader("Top Cryptocurrencies")
    
    # Create dataframe for the table
    top_coins_data = []
    for i, coin in enumerate(coins[:20], 1):  # Display top 20
        top_coins_data.append({
            "#": i,
            "Coin": coin['name'],
            "Symbol": coin['symbol'].upper(),
            "Price": f"${coin['current_price']:.2f}",
            "24h Change": f"{coin.get('price_change_percentage_24h', 0):.2f}%",
            "Market Cap": format_large_number(coin.get('market_cap')),
            "Volume (24h)": format_large_number(coin.get('total_volume'))
        })
    
    df = pd.DataFrame(top_coins_data)
    
    # Custom styling for the table
    st.dataframe(
        df,
        hide_index=True,
        column_config={
            "#": st.column_config.NumberColumn(format="%d"),
            "24h Change": st.column_config.Column(
                width="medium",
            ),
        },
        height=600
    )
    
    # Search functionality
    st.subheader("Search Cryptocurrencies")
    
    # Create search input
    search_query = st.text_input("Search by name or symbol", "")
    
    if search_query:
        # Filter coins based on search query
        search_results = [
            coin for coin in coins
            if search_query.lower() in coin['name'].lower() or search_query.lower() in coin['symbol'].lower()
        ]
        
        if search_results:
            # Create dataframe for search results
            search_results_data = []
            for coin in search_results:
                search_results_data.append({
                    "Coin": coin['name'],
                    "Symbol": coin['symbol'].upper(),
                    "Price": f"${coin['current_price']:.2f}",
                    "24h Change": f"{coin.get('price_change_percentage_24h', 0):.2f}%",
                    "Market Cap": format_large_number(coin.get('market_cap')),
                    "Volume (24h)": format_large_number(coin.get('total_volume'))
                })
            
            search_df = pd.DataFrame(search_results_data)
            st.dataframe(search_df, hide_index=True)
        else:
            st.info("No results found. Try a different search term.")

#############################################
# MAIN APP
#############################################

# Sidebar navigation
st.sidebar.title("Crypto Tracker")
st.sidebar.markdown("Track cryptocurrencies in real-time.")

# Navigation options
page_options = {
    "Dashboard": "home",
    "Portfolio": "portfolio",
    "Watchlist": "watchlist",
    "Market Overview": "market"
}

selected_page = st.sidebar.radio("Navigation", list(page_options.keys()))

# Add sidebar info
st.sidebar.markdown("---")
st.sidebar.info(
    "This app uses the CoinGecko API to track cryptocurrency prices and market data."
)
st.sidebar.markdown("---")
st.sidebar.caption("Developed with Streamlit")

# Load the selected page
if page_options[selected_page] == "home":
    home_dashboard()
elif page_options[selected_page] == "portfolio":
    portfolio_page()
elif page_options[selected_page] == "watchlist":
    watchlist_page()
elif page_options[selected_page] == "market":
    market_page()

# Add footer
st.markdown("---")
st.caption("Data provided by CoinGecko API. Prices update every minute.")