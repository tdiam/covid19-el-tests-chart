from copy import deepcopy
from datetime import datetime
from pathlib import Path
from shutil import copyfile

import requests as r


API_URL = 'https://covid-19-greece.herokuapp.com'

class DailyTests:
    def __init__(self):
        self.data = []
        self.groups = []

    def load(self):
        res = r.get(f'{API_URL}/total-tests')
        # TODO: Handle error
        api_data = res.json()['total_tests']
        
        prev = 0
        for d in api_data:
            cumulative_tests = prev if d['tests'] is None else d['tests']
            self.data.append({
                'date': d['date'],
                'daily_tests': cumulative_tests - prev,
                'reported_tests': d['tests'] is not None,
                'cumulative_tests': cumulative_tests,
                'corrected': False,
            })
            prev = cumulative_tests

    def run_corrections(self):
        """
        Get groups (cases where there was one report for multiple
        days). Distribute number of tests on grouped days.
        """
        # June 3-4
        total = None
        for d in self.data:
            if d['date'] == '2020-06-03':
                total = d['daily_tests']
                self.groups.append({
                    'total_tests': total,
                    'from': '2020-06-03',
                    'to': '2020-06-04',
                })
            if d['date'] in ['2020-06-03', '2020-06-04']:
                assert(total is not None)
                d['daily_tests'] = total / 2
                d['corrected'] = True

        # June 5-8
        total = None
        for d in self.data:
            if d['date'] == '2020-06-05':
                total = d['daily_tests']
                self.groups.append({
                    'total_tests': total,
                    'from': '2020-06-05',
                    'to': '2020-06-08',
                })
            if d['date'] in ['2020-06-05', '2020-06-06', '2020-06-07', '2020-06-08']:
                assert(total is not None)
                d['daily_tests'] = total / 4
                d['corrected'] = True

    def build_weekly_ma(self):
        # Must be odd
        window_len = 7
        # Half of window
        half = window_len // 2
        mas = half * [None]
        i = half
        while i < len(self.data) - half:
            window = [d['daily_tests'] for d in self.data[i-half : i+half+1]]
            ma = round(sum(window) / window_len)
            mas.append(ma)
            i += 1
        mas.extend(half * [None])
        self.weekly_mas = mas

    def plot(self, save=True):
        """
        Plot the data.

        Arguments
        ---------
        save : bool
            If True the plot will be saved in the `plots/` directory.
        """
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt

        xs = list(range(len(self.data)))
        ys = [d['daily_tests'] for d in self.data]
        dates = [d['date'] for d in self.data]

        plt.figure(figsize=(20, 10))
        plt.suptitle(f'Ημερήσια τεστ COVID-19 στην Ελλάδα ' \
                f'({dates[0]} έως {dates[-1]})', y=0.93)
        plt.title('Πηγή: Υπολογισμός διαφορών από τους αριθμούς ' \
                'συνολικών τεστ των επιδημιολογικών αναφορών του ' \
                'ΕΟΔΥ', fontsize=9)
        bar_container = plt.bar(xs, ys, color='#2283C9')
        plt.xticks(xs[::2], labels=dates[::2], rotation=90)
        max_height = max(ys)
        for idx, rect in enumerate(bar_container):
            if self.data[idx]['corrected']:
                rect.set_visible(False)
                continue

            date = datetime.strptime(dates[idx], '%Y-%m-%d').date()
            if date.weekday() in [0, 6]:
                rect.set_facecolor('#175A8A')

            height = rect.get_height()
            text_y = height + 0.01 * max_height
            rotation = 90 if ys[idx] >= 0 else 0
            if ys[idx] < 0:
                text_y -= 350
            plt.text(rect.get_x() + rect.get_width() / 2.0,
                    text_y, ys[idx], ha='center', va='bottom',
                    fontsize=6, rotation=rotation)

        # Groups plot
        date_to_idx = dict(zip(dates, xs))
        for g in self.groups:
            xstart = date_to_idx[g['from']]
            xend = date_to_idx[g['to']]
            xmid = (xstart + xend) / 2
            xlen = xend - xstart + 1
            height = g['total_tests'] / xlen
            width = xlen - 0.2 # margin
            plt.bar([xmid], height, width=width, facecolor='#B1D7F2',
                    edgecolor='#1F78B7', hatch='\\\\')

            text_y = height + 0.01 * max_height
            rotation = 90 if height >= 0 else 0
            if height < 0:
                text_y -= 350
            plt.text(xmid, text_y, g['total_tests'], ha='center',
                    va='bottom', fontsize=6, rotation=rotation)

        # Moving average plot
        plt.plot(xs, self.weekly_mas, '#FFA500', linewidth=3)

        normal_patch = mpatches.Patch(color='#2283C9',
                label='Κανονικές ημέρες')
        weekend_patch = mpatches.Patch(color='#175A8A',
                label='Σάββατο 15:00-Δευτέρα 15:00 (μειωμένοι ' \
                'έλεγχοι στα ΣΚ)')
        grouped_patch = mpatches.Patch(facecolor='#B1D7F2',
                edgecolor='#1F78B7', hatch='\\\\\\',
                label='Ομαδοποιημένες ημέρες (πχ. 5-8 Ιουνίου)')
        ma_patch = mpatches.Patch(facecolor='#FFA500',
                label='Κινητός μέσος όρος 7 ημερών')
        plt.legend(handles=[
            normal_patch, weekend_patch, grouped_patch, ma_patch
        ], loc='lower left')

        fig = plt.gcf()
        plt.show()

        # Save
        if save:
            plot_dir = Path('plots')
            plot_dir.mkdir(exist_ok=True)
            plot_filename = f'covid19-el-tests-{dates[-1]}.png'
            fig.savefig(plot_dir / plot_filename)
            # Update latest plot to use this
            copyfile(plot_dir / plot_filename, plot_dir / 'latest.png')


if __name__ == '__main__':
    dt = DailyTests()
    dt.load()
    dt.run_corrections()
    dt.build_weekly_ma()
    dt.plot()

