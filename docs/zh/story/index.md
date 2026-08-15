# 故事

<script setup>
import { withBase } from "vitepress";
</script>

<div class="story-scroll" data-story-scroll>
  <aside class="story-timeline" aria-label="故事进度">
    <span class="story-timeline__line" aria-hidden="true"></span>
    <a class="story-timeline__dot is-active" href="#story-signal" aria-label="发现信号"><span>01</span></a>
    <a class="story-timeline__dot" href="#story-confirmation" aria-label="确认彼此存在"><span>02</span></a>
    <a class="story-timeline__dot" href="#story-preparation" aria-label="双方准备"><span>03</span></a>
    <a class="story-timeline__dot" href="#story-arrival" aria-label="计划开始"><span>04</span></a>
    <a class="story-timeline__dot" href="#story-life" aria-label="共同生活"><span>05</span></a>
    <a class="story-timeline__dot" href="#story-world" aria-label="世界变大"><span>06</span></a>
    <a class="story-timeline__dot" href="#story-invitation" aria-label="加入故事"><span>07</span></a>
  </aside>

  <section class="story-chapter story-chapter--opening" id="story-signal" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-01-signal.png')" alt="一条信号穿过深空，向地球传来。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>我们听到了一个来自深空的信号</h2>
    </div>
  </section>

  <section class="story-chapter" id="story-confirmation" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-02-confirmation.png')" alt="地球和 Elfaria 在星空两端互相回应。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>初次接触之后，我们确认了彼此的存在</h2>
    </div>
  </section>

  <section class="story-chapter" id="story-preparation" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-03-preparation.png')" alt="地球在建造基站，Elfaria 上的 Elfie 正在报名。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>我们在地球建起了基站<br />而他们发起了赴地计划</h2>
    </div>
  </section>

  <section class="story-chapter" id="story-arrival" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-04-arrival.png')" alt="一只 Elfie 出现在人类家中的玻璃精灵巢里。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>只要在家里准备好一个 ElfieNest<br />就有机会迎来一只 Elfie 来到你的身边</h2>
    </div>
  </section>

  <section class="story-chapter" id="story-life" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-05-life.png')" alt="Elfie 在精灵巢里玩耍，人类拿着玩具和它互动。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>你们将一起生活、一起玩耍<br />一个来自远方的生命，会成为你生活的一部分</h2>
    </div>
  </section>

  <section class="story-chapter" id="story-world" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-06-world.png')" alt="越来越多的精灵巢在地球与 Elfaria 之间连接起来。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>随着越来越多的 Elfie 来到地球<br />我们将一起探索更大的世界</h2>
    </div>
  </section>

  <section class="story-chapter story-chapter--closing" id="story-invitation" data-story-chapter>
    <img class="story-chapter__image" :src="withBase('/assets/story/story-07-invitation.png')" alt="一只 Elfie 站在温暖家门前，邀请我们开始这段故事。" />
    <div class="story-chapter__veil" aria-hidden="true"></div>
    <div class="story-chapter__copy">
      <h2>你愿意为一个 Elfie 留一个位置吗？</h2>
    </div>
  </section>
</div>

如果你想知道这座基站是怎样被构建的，可以继续阅读[开发者文档](../developer/)。
