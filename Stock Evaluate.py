import yfinance as yf
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
from get_all_tickers import get_tickers as gt
import telebot
import multiprocessing
from yahoofinancials import YahooFinancials

growth_rate = 0.12
min_rate_of_return = 0.15
margin_of_safety = 0.5
est_PE_ratio = growth_rate * 1.25 * 100

yahoo_financials_rf = YahooFinancials('^TNX')
Rf = yahoo_financials_rf.get_current_price()
Rm = 5.6 # As of 2020, US Market Premium
perpetual_growth = 0.025

def DiscountedCashflow(ticker):
  try:
    yahoo_financials = YahooFinancials(ticker)
    if (isCashflowPositive(ticker, yahoo_financials)):
      annual_cashflow_stmt = yahoo_financials.get_financial_stmts('annual', 'cash')['cashflowStatementHistory'][ticker]
      annual_balance_stmt = yahoo_financials.get_financial_stmts('annual', 'balance')['balanceSheetHistory'][ticker]
      annual_income_stmt = yahoo_financials.get_financial_stmts('annual', 'income')['incomeStatementHistory'][ticker]
      summary_data = yahoo_financials.get_summary_data()[ticker]

      total_CO_list = getFinancialInfoList(annual_cashflow_stmt, 'totalCashFromOperatingActivities')
      capEx_list = getFinancialInfoList(annual_cashflow_stmt, 'capitalExpenditures')

      free_cashflow_list = [x + y for x, y in zip(total_CO_list, capEx_list)]

      # Only predict more than 4 years !
      if (len(free_cashflow_list) < 4):
          return 0

      avg_cashflow_growth = (free_cashflow_list[0] - free_cashflow_list[-1]) / len(free_cashflow_list)
      
      # next 4 years prediction
      predict_free_cashflow_list = []
      for i in range(4):
        if (len(predict_free_cashflow_list) == 0):
          predict_free_cashflow_list.append(free_cashflow_list[0] + avg_cashflow_growth)
        else:
          predict_free_cashflow_list.append(predict_free_cashflow_list[i-1] + avg_cashflow_growth)

        if(i < 3):
          avg_cashflow_growth = (predict_free_cashflow_list[i] - free_cashflow_list[-2-i])/4

      wacc = getWACC(yahoo_financials, annual_balance_stmt, annual_income_stmt)

      # Calculate Terminal Value
      terminal_value = predict_free_cashflow_list[-1] * ((1 + perpetual_growth)/(wacc/100 - perpetual_growth))

      # Calculate Discount Factor
      discount_factor = []
      for i in range(4):
        discount_factor.append(pow(1 + wacc/100, i+1))
      
      PV_list = [x / y for x, y in zip(predict_free_cashflow_list, discount_factor)]
      PV_of_FCF = sum(PV_list) + (terminal_value / discount_factor[-1])
      market_cap = summary_data['marketCap']
      actual_stock_price = yahoo_financials.get_current_price()
      share_outstanding = market_cap / actual_stock_price
      calculated_stock_price = PV_of_FCF / share_outstanding
      
      if(calculated_stock_price > actual_stock_price):
        print('[' + ticker + '] ' + str("{:.2f}".format((calculated_stock_price - actual_stock_price)/actual_stock_price*100)) + ' percent, calculated price: ' + str("{:.2f}".format(calculated_stock_price)) + ' and actual price: ' + str(actual_stock_price))
  except:
    pass
  
def getWACC(yahoo_financials, annual_balance_stmt, annual_income_stmt):
  # debt and equity
  total_stockholder_equity_list = getFinancialInfoList(annual_balance_stmt, 'totalStockholderEquity')
  long_term_debt_list = getFinancialInfoList(annual_balance_stmt, 'longTermDebt')
  total_liabilities_list = getFinancialInfoList(annual_balance_stmt, 'totalLiab')

  equity = total_stockholder_equity_list[0]
  long_term_debt = long_term_debt_list[0]
  total_liabilities = total_liabilities_list[0]

  # cost of equity
  Ba = yahoo_financials.get_beta()
  cost_of_equity = Rf + Ba * Rm

  # cost of debt = interest expenses / total debt * 100
  interest_expenses_list = getFinancialInfoList(annual_income_stmt, 'interestExpense')

  cost_of_debt = -interest_expenses_list[0] / total_liabilities * 100

  income_before_tax_list = getFinancialInfoList(annual_income_stmt, 'incomeBeforeTax')
  net_income_list = getFinancialInfoList(annual_income_stmt, 'netIncome')
  tax_rate = 1 - (income_before_tax_list[0]/net_income_list[0])

  wacc = (equity / (equity+long_term_debt) * cost_of_equity) + (long_term_debt / (equity+long_term_debt) * cost_of_debt * (1 - tax_rate))

  return wacc

def getFinancialInfoList(stmt, header):
  full_list = []
  for st in stmt:
    for y in st:
      full_list.append(st[y][header])

  return full_list

def isCashflowPositive(ticker, yahoo_financials):
  list = yahoo_financials.get_financial_stmts('quarterly', 'cash')['cashflowStatementHistoryQuarterly'][ticker]
  
  isCashflowNegativeByYear = 0

  for item in list:
    for y in item:
      if (item[y]['totalCashFromOperatingActivities'] < 0):
        isCashflowNegativeByYear = isCashflowNegativeByYear + 1 

  return isCashflowNegativeByYear < 2

if __name__ == "__main__":  
  # DiscountedCashflow('MSFT')

  #Get the stock quote
  tickers = gt.get_tickers(AMEX=False)
  sector_filtered_tickers = gt.get_tickers_filtered(sectors=[gt.SectorConstants.HEALTH_CARE, gt.SectorConstants.TECH, gt.SectorConstants.SERVICES])
  ticker_list = list(set(tickers) & set(sector_filtered_tickers))

  print("Total Tickers: " + str(len(ticker_list)))
  print("Total Cores: " + str(multiprocessing.cpu_count()))
  pool = multiprocessing.Pool(multiprocessing.cpu_count())
  results = pool.map(DiscountedCashflow, ticker_list)

